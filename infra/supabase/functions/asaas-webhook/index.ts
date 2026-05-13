// Edge Function que recebe webhooks do Asaas e sincroniza a tabela
// `subscribers` no Supabase. Roteia eventos de assinatura/cobrança:
//
//   - PAYMENT_CONFIRMED / PAYMENT_RECEIVED -> active=true, valid_until=nextDue+7d
//   - SUBSCRIPTION_CREATED                 -> active=false (ainda não pagou)
//   - SUBSCRIPTION_INACTIVATED/DELETED     -> active=false
//   - PAYMENT_OVERDUE                      -> active=false (atrasou)
//
// Pra ativar um usuário, busca o e-mail dele no Asaas (GET /customers/:id),
// cria o auth.user via Supabase Admin API (se não existir) e faz upsert.
//
// Segurança: valida o header `asaas-access-token` contra o secret
// ASAAS_WEBHOOK_TOKEN. Se não bater, responde 401.
//
// Idempotência: usa `upsert` na tabela. Webhooks repetidos do mesmo evento
// resultam no mesmo estado final.
//
// Deploy:
//   supabase functions deploy asaas-webhook --no-verify-jwt
//   (--no-verify-jwt porque o Asaas não autentica com JWT do Supabase;
//   autenticamos manualmente via asaas-access-token header)

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// ── Config (Supabase secrets) ────────────────────────────────────────────────
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ASAAS_WEBHOOK_TOKEN = Deno.env.get("ASAAS_WEBHOOK_TOKEN")!;
const ASAAS_API_KEY = Deno.env.get("ASAAS_API_KEY")!;
const ASAAS_ENV = (Deno.env.get("ASAAS_ENV") ?? "sandbox").toLowerCase();

// E-mail de boas-vindas (Resend) — opcional; se RESEND_API_KEY não estiver
// definido, o envio é skipado silenciosamente.
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const WELCOME_EMAIL_FROM = Deno.env.get("WELCOME_EMAIL_FROM") ??
  "App Iter <onboarding@resend.dev>";
const DOWNLOAD_URL = Deno.env.get("APP_DOWNLOAD_URL") ??
  "https://github.com/giuseppeferretti/app-iter/releases/latest/download/AppIter_Setup.exe";
const SUPPORT_EMAIL = Deno.env.get("SUPPORT_EMAIL") ?? "suporte.iter@gmail.com";

const ASAAS_API_BASE = ASAAS_ENV === "production"
  ? "https://api.asaas.com/v3"
  : "https://api-sandbox.asaas.com/v3";

// Client com SERVICE_ROLE — bypassa RLS, pode escrever em subscribers e
// chamar a Admin API.
const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

// ── Helpers ──────────────────────────────────────────────────────────────────

interface AsaasEventPayload {
  id?: string;
  event: string;
  dateCreated?: string;
  payment?: {
    id?: string;
    customer?: string;
    subscription?: string;
    value?: number;
    dueDate?: string;
    status?: string;
  };
  subscription?: {
    id?: string;
    customer?: string;
    value?: number;
    nextDueDate?: string;
    status?: string;
  };
}

interface AsaasCustomer {
  id: string;
  name?: string;
  email?: string;
  cpfCnpj?: string;
}

async function asaasGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${ASAAS_API_BASE}${path}`, {
    headers: {
      "access_token": ASAAS_API_KEY,
      "Content-Type": "application/json",
    },
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Asaas API ${path} retornou ${resp.status}: ${txt}`);
  }
  return await resp.json() as T;
}

function parseDataPtBr(s?: string): Date | null {
  // Asaas devolve datas em "DD/MM/YYYY" (subscription.nextDueDate) ou
  // "YYYY-MM-DD" (payment.dueDate). Tentamos os dois formatos.
  if (!s) return null;
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return new Date(s);
  const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (m) return new Date(`${m[3]}-${m[2]}-${m[1]}`);
  return null;
}

function addDias(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

async function buscarOuCriarAuthUser(email: string): Promise<string> {
  // 1. Tenta achar usuário existente
  // listUsers tem paginação; pra base pequena (até 1000) basta a primeira página.
  const { data: lista, error: listErr } = await supabaseAdmin.auth.admin
    .listUsers({
      page: 1,
      perPage: 200,
    });
  if (listErr) throw listErr;

  const existente = lista.users.find((u) =>
    (u.email ?? "").toLowerCase() === email.toLowerCase()
  );
  if (existente) return existente.id;

  // 2. Cria. email_confirm=true evita exigir confirmação manual — o cliente
  // pagou, já confirmamos o e-mail.
  const { data, error } = await supabaseAdmin.auth.admin.createUser({
    email,
    email_confirm: true,
  });
  if (error) throw error;
  if (!data.user) throw new Error("Supabase não retornou user após createUser");
  return data.user.id;
}

type AcaoSubscriber = "activate" | "deactivate" | "neutral";

async function upsertSubscriber(opts: {
  userId: string;
  email: string;
  acao: AcaoSubscriber;
  validUntil: Date | null;
  asaasCustomerId?: string;
  asaasSubscriptionId?: string;
  ultimoEvento: string;
}) {
  // Pra eventos "neutros" (PAYMENT_CREATED, SUBSCRIPTION_CREATED) NÃO devemos
  // rebaixar active=true pra false. Esses eventos chegam depois de um
  // PAYMENT_CONFIRMED no link de pagamento Asaas e iam sobrescrever o estado
  // ativado. Solução: SELECT antes pra preservar active atual em eventos neutros.
  let active: boolean;
  let validUntilToWrite: string | null = opts.validUntil
    ? opts.validUntil.toISOString()
    : null;

  if (opts.acao === "neutral") {
    const { data: atual } = await supabaseAdmin
      .from("subscribers")
      .select("active, valid_until")
      .eq("user_id", opts.userId)
      .maybeSingle();
    active = atual?.active ?? false;
    // Preserva valid_until existente se o evento neutro não trouxe um novo
    if (!validUntilToWrite && atual?.valid_until) {
      validUntilToWrite = atual.valid_until;
    }
  } else {
    active = opts.acao === "activate";
  }

  const { error } = await supabaseAdmin
    .from("subscribers")
    .upsert({
      user_id: opts.userId,
      email: opts.email,
      active,
      valid_until: validUntilToWrite,
      asaas_customer_id: opts.asaasCustomerId ?? null,
      asaas_subscription_id: opts.asaasSubscriptionId ?? null,
      ultimo_evento: opts.ultimoEvento,
    }, { onConflict: "user_id" });
  if (error) throw error;
  return active;
}

// ── E-mail de boas-vindas via Resend ─────────────────────────────────────────

function montarEmailHtml(email: string): { subject: string; html: string; text: string } {
  const subject = "Bem-vindo ao App Iter — baixe o aplicativo";
  const html = `<!doctype html>
<html lang="pt-BR">
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0c0c10;color:#e8e8ed;padding:40px 20px;margin:0;">
    <div style="max-width:560px;margin:0 auto;background:#15151c;border-radius:12px;padding:36px 32px;border:1px solid rgba(255,255,255,0.06);">
      <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.22em;color:rgba(255,255,255,0.55);text-transform:uppercase;margin-bottom:24px;">
        App Iter
      </div>
      <h1 style="font-size:24px;line-height:1.3;color:#fff;margin:0 0 18px 0;font-weight:600;">
        Sua assinatura está ativa.
      </h1>
      <p style="font-size:15px;line-height:1.55;color:rgba(255,255,255,0.78);margin:0 0 28px 0;">
        Pagamento confirmado. Você já pode baixar o App Iter e começar a automatizar o lançamento de horas no SACI.
      </p>

      <div style="margin:32px 0;">
        <a href="${DOWNLOAD_URL}"
           style="display:inline-block;background:#5b5bf0;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:15px;">
          Baixar AppIter_Setup.exe
        </a>
      </div>

      <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:20px 22px;margin:28px 0;">
        <div style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:0.22em;color:rgba(255,255,255,0.45);text-transform:uppercase;margin-bottom:12px;">
          Próximos passos
        </div>
        <ol style="margin:0;padding-left:20px;color:rgba(255,255,255,0.78);font-size:14px;line-height:1.7;">
          <li>Execute o instalador. O Windows pode mostrar um aviso de "editor desconhecido" — clique em <b>Mais informações</b> &rsaquo; <b>Executar mesmo assim</b>.</li>
          <li>Abra o App Iter no menu Iniciar.</li>
          <li>Na tela de licença, digite <b>${email}</b> (o mesmo e-mail que você usou no pagamento).</li>
          <li>Você receberá um código de 6 dígitos por e-mail. Cole na tela do app pra entrar.</li>
        </ol>
      </div>

      <p style="font-size:13px;line-height:1.55;color:rgba(255,255,255,0.55);margin:24px 0 0 0;">
        Qualquer dúvida, responda este e-mail ou escreva para
        <a href="mailto:${SUPPORT_EMAIL}" style="color:#9a9aff;text-decoration:none;">${SUPPORT_EMAIL}</a>.
      </p>

      <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:32px 0 20px 0;">
      <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:0.18em;color:rgba(255,255,255,0.35);text-transform:uppercase;margin:0;">
        Iter · App ANAC · 2026
      </p>
    </div>
  </body>
</html>`;
  const text = `Sua assinatura do App Iter está ativa.

Baixe o aplicativo: ${DOWNLOAD_URL}

Próximos passos:
1. Execute o instalador (clique em "Mais informações" > "Executar mesmo assim" se aparecer aviso do Windows).
2. Abra o App Iter no menu Iniciar.
3. Na tela de licença, digite ${email} (o e-mail do pagamento).
4. Cole o código de 6 dígitos que você recebe por e-mail.

Suporte: ${SUPPORT_EMAIL}
`;
  return { subject, html, text };
}

async function enviarEmailBoasVindas(email: string): Promise<boolean> {
  if (!RESEND_API_KEY) {
    console.log("[asaas-webhook] RESEND_API_KEY não configurado — skip do e-mail");
    return false;
  }
  const { subject, html, text } = montarEmailHtml(email);
  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: WELCOME_EMAIL_FROM,
      to: [email],
      subject,
      html,
      text,
    }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Resend retornou ${resp.status}: ${body}`);
  }
  return true;
}

async function dispararBoasVindasSeNecessario(opts: {
  userId: string;
  email: string;
}): Promise<"sent" | "skipped" | "already-sent" | "failed"> {
  // Idempotência: só envia se welcome_email_sent_at for null
  const { data, error } = await supabaseAdmin
    .from("subscribers")
    .select("welcome_email_sent_at")
    .eq("user_id", opts.userId)
    .maybeSingle();
  if (error) {
    console.error(`[asaas-webhook] erro ao ler welcome_email_sent_at:`, error);
    return "failed";
  }
  if (data?.welcome_email_sent_at) {
    return "already-sent";
  }

  try {
    const enviado = await enviarEmailBoasVindas(opts.email);
    if (!enviado) return "skipped";
  } catch (e) {
    console.error(`[asaas-webhook] erro ao enviar e-mail Resend:`, e);
    return "failed";
  }

  // Marca como enviado. Se falhar, no próximo webhook do mesmo evento o
  // upsert é idempotente mas o e-mail seria reenviado — preferimos tolerar
  // reenvio raro a deixar cliente sem e-mail.
  const { error: updErr } = await supabaseAdmin
    .from("subscribers")
    .update({ welcome_email_sent_at: new Date().toISOString() })
    .eq("user_id", opts.userId);
  if (updErr) {
    console.error(`[asaas-webhook] erro ao marcar welcome_email_sent_at:`, updErr);
  }
  return "sent";
}

// ── Handler principal ───────────────────────────────────────────────────────

Deno.serve(async (req: Request) => {
  // Health check
  if (req.method === "GET") {
    return new Response(
      JSON.stringify({ ok: true, service: "asaas-webhook" }),
      {
        headers: { "Content-Type": "application/json" },
      },
    );
  }
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  // 1. Autentica via header asaas-access-token
  const token = req.headers.get("asaas-access-token") ?? "";
  if (!ASAAS_WEBHOOK_TOKEN || token !== ASAAS_WEBHOOK_TOKEN) {
    return new Response("Unauthorized", { status: 401 });
  }

  // 2. Parse payload
  let body: AsaasEventPayload;
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const evento = (body.event ?? "").toUpperCase();
  console.log(`[asaas-webhook] event=${evento} id=${body.id ?? "?"}`);

  // 3. Determina customer + subscription id e ação
  const payment = body.payment;
  const subscription = body.subscription;
  const customerId = payment?.customer ?? subscription?.customer;
  const subscriptionId = payment?.subscription ?? subscription?.id;

  if (!customerId) {
    console.log("[asaas-webhook] evento sem customer — ignorando");
    return new Response("Ignored (no customer)", { status: 200 });
  }

  // Eventos que ATIVAM o usuário
  const eventosAtivam = new Set([
    "PAYMENT_CONFIRMED",
    "PAYMENT_RECEIVED",
    "PAYMENT_CHARGEBACK_REVERSED",
  ]);
  // Eventos que DESATIVAM o usuário
  const eventosDesativam = new Set([
    "PAYMENT_OVERDUE",
    "PAYMENT_REFUNDED",
    "PAYMENT_CHARGEBACK_REQUESTED",
    "PAYMENT_DELETED",
    "SUBSCRIPTION_INACTIVATED",
    "SUBSCRIPTION_DELETED",
  ]);
  // Eventos de criação de assinatura — não ativam, mas registram
  const eventosCriam = new Set([
    "SUBSCRIPTION_CREATED",
    "PAYMENT_CREATED",
  ]);

  if (
    !eventosAtivam.has(evento) &&
    !eventosDesativam.has(evento) &&
    !eventosCriam.has(evento)
  ) {
    console.log(`[asaas-webhook] evento ${evento} não tratado — ack 200`);
    return new Response("OK (untracked event)", { status: 200 });
  }

  // 4. Busca dados do customer no Asaas (pra pegar o e-mail)
  let customer: AsaasCustomer;
  try {
    customer = await asaasGet<AsaasCustomer>(`/customers/${customerId}`);
  } catch (e) {
    console.error(`[asaas-webhook] erro ao buscar customer ${customerId}:`, e);
    return new Response(`Erro Asaas: ${(e as Error).message}`, { status: 502 });
  }
  const email = (customer.email ?? "").trim().toLowerCase();
  if (!email) {
    console.error(`[asaas-webhook] customer ${customerId} sem email`);
    return new Response("Customer sem email", { status: 200 });
  }

  // 5. Garante user no auth.users
  let userId: string;
  try {
    userId = await buscarOuCriarAuthUser(email);
  } catch (e) {
    console.error(`[asaas-webhook] erro ao criar auth user:`, e);
    return new Response(`Erro Supabase: ${(e as Error).message}`, {
      status: 500,
    });
  }

  // 6. Calcula valid_until baseado no nextDueDate + 7 dias de grace
  const nextDue = parseDataPtBr(subscription?.nextDueDate ?? payment?.dueDate);
  const validUntil = nextDue ? addDias(nextDue, 7) : null;

  // 7. Decide ação:
  //    - activate   → escreve active=true (sobrepõe estado anterior)
  //    - deactivate → escreve active=false
  //    - neutral    → preserva active atual (SUBSCRIPTION_CREATED/PAYMENT_CREATED
  //                   chegam depois de um PAYMENT_CONFIRMED e não devem rebaixar)
  let acao: AcaoSubscriber;
  if (eventosAtivam.has(evento)) acao = "activate";
  else if (eventosDesativam.has(evento)) acao = "deactivate";
  else acao = "neutral";

  // 8. Upsert
  let finalActive = false;
  try {
    finalActive = await upsertSubscriber({
      userId,
      email,
      acao,
      validUntil,
      asaasCustomerId: customerId,
      asaasSubscriptionId: subscriptionId,
      ultimoEvento: evento,
    });
  } catch (e) {
    console.error(`[asaas-webhook] erro upsert subscribers:`, e);
    return new Response(`Erro DB: ${(e as Error).message}`, { status: 500 });
  }

  // 9. Dispara e-mail de boas-vindas se foi uma ATIVAÇÃO bem-sucedida
  //    (idempotente — só envia se welcome_email_sent_at IS NULL).
  let emailStatus: "sent" | "skipped" | "already-sent" | "failed" | "n/a" = "n/a";
  if (acao === "activate" && finalActive) {
    emailStatus = await dispararBoasVindasSeNecessario({ userId, email });
  }

  console.log(
    `[asaas-webhook] OK email=${email} acao=${acao} active=${finalActive} valid_until=${
      validUntil?.toISOString() ?? "null"
    } welcome_email=${emailStatus}`,
  );
  return new Response(
    JSON.stringify({
      ok: true,
      email,
      acao,
      active: finalActive,
      valid_until: validUntil,
      welcome_email: emailStatus,
    }),
    { headers: { "Content-Type": "application/json" } },
  );
});
