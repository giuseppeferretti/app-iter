// Edge Function `reenviar-email`
//
// Endpoint público pro site app-anac chamar quando o cliente perde o e-mail
// de boas-vindas. Recebe { email } no POST e:
//   1. Valida o e-mail (formato, presença em `subscribers` com active=true)
//   2. Re-dispara o e-mail via Resend
//   3. Rate limit por IP (5 req/hora) pra evitar abuso
//
// CORS permitido pro domínio app-anac.vercel.app (+ futuro custom domain).
//
// Deploy:
//   supabase functions deploy reenviar-email --no-verify-jwt
//
// Secrets necessários (já compartilhados com asaas-webhook):
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
//   RESEND_API_KEY, WELCOME_EMAIL_FROM,
//   APP_DOWNLOAD_URL, APP_TUTORIAL_URL, SUPPORT_EMAIL

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const WELCOME_EMAIL_FROM = Deno.env.get("WELCOME_EMAIL_FROM") ??
  "App Iter <onboarding@resend.dev>";
const DOWNLOAD_URL = Deno.env.get("APP_DOWNLOAD_URL") ??
  "https://github.com/giuseppeferretti/app-iter/releases/latest/download/AppIter_Setup.exe";
const TUTORIAL_URL = Deno.env.get("APP_TUTORIAL_URL") ??
  "https://github.com/giuseppeferretti/app-iter/releases/latest/download/tutorial_planilha.pdf";
const SUPPORT_EMAIL = Deno.env.get("SUPPORT_EMAIL") ?? "suporte.iter@gmail.com";

const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

// Rate limit em memória — reinicia a cada cold start, mas suficiente pra
// abuso casual. Pra rate limit persistente, usar tabela Postgres.
const rateLimitStore = new Map<string, number[]>();
const RATE_LIMIT_MAX = 5;
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000; // 1 hora

function checarRateLimit(ip: string): boolean {
  const agora = Date.now();
  const tentativas = (rateLimitStore.get(ip) ?? []).filter(
    (ts) => agora - ts < RATE_LIMIT_WINDOW_MS,
  );
  if (tentativas.length >= RATE_LIMIT_MAX) return false;
  tentativas.push(agora);
  rateLimitStore.set(ip, tentativas);
  return true;
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function montarEmailHtml(email: string): { subject: string; html: string; text: string } {
  const subject = "Seu link do App Iter — instalador + tutorial";
  const html = `<!doctype html>
<html lang="pt-BR">
  <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0c0c10;color:#e8e8ed;padding:40px 20px;margin:0;">
    <div style="max-width:560px;margin:0 auto;background:#15151c;border-radius:12px;padding:36px 32px;border:1px solid rgba(255,255,255,0.06);">
      <div style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.22em;color:rgba(255,255,255,0.55);text-transform:uppercase;margin-bottom:24px;">
        App Iter · Link Reenviado
      </div>
      <h1 style="font-size:22px;line-height:1.3;color:#fff;margin:0 0 16px 0;font-weight:600;">
        Aqui está seu link de novo.
      </h1>
      <p style="font-size:15px;line-height:1.55;color:rgba(255,255,255,0.78);margin:0 0 24px 0;">
        Você pediu pra reenviar o link do App Iter pra <b>${email}</b>. Aqui vai:
      </p>

      <div style="margin:28px 0;">
        <a href="${DOWNLOAD_URL}"
           style="display:inline-block;background:#5b5bf0;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:15px;margin-right:10px;">
          Baixar o App (.exe)
        </a>
        <a href="${TUTORIAL_URL}"
           style="display:inline-block;background:transparent;color:#fff;text-decoration:none;padding:13px 26px;border-radius:8px;font-weight:600;font-size:15px;border:1px solid rgba(255,255,255,0.25);">
          Baixar o Tutorial (PDF)
        </a>
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
  const text = `Aqui está seu link do App Iter de novo (${email}):

Aplicativo:  ${DOWNLOAD_URL}
Tutorial:    ${TUTORIAL_URL}

Suporte: ${SUPPORT_EMAIL}
`;
  return { subject, html, text };
}

async function enviarEmail(email: string): Promise<void> {
  if (!RESEND_API_KEY) {
    throw new Error("RESEND_API_KEY não configurado.");
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
    throw new Error(`Resend retornou ${resp.status}: ${await resp.text()}`);
  }
}

Deno.serve(async (req: Request) => {
  // Preflight CORS
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: CORS_HEADERS });
  }

  // Rate limit por IP
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim()
    ?? req.headers.get("cf-connecting-ip")
    ?? "unknown";
  if (!checarRateLimit(ip)) {
    return new Response(
      JSON.stringify({ ok: false, erro: "Muitas tentativas. Aguarde 1 hora." }),
      { status: 429, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
    );
  }

  let body: { email?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(
      JSON.stringify({ ok: false, erro: "JSON inválido." }),
      { status: 400, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
    );
  }

  const email = (body.email ?? "").trim().toLowerCase();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return new Response(
      JSON.stringify({ ok: false, erro: "E-mail inválido." }),
      { status: 400, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
    );
  }

  // Verifica se o e-mail existe em subscribers e está ativo
  // Política: SEMPRE retornamos sucesso pra não vazar quais e-mails são
  // clientes vs não — mas só enviamos de fato se ele estiver ativo.
  const { data: sub } = await supabaseAdmin
    .from("subscribers")
    .select("email, active")
    .eq("email", email)
    .maybeSingle();

  if (sub && sub.active) {
    try {
      await enviarEmail(email);
      console.log(`[reenviar-email] enviado pra ${email}`);
    } catch (exc) {
      console.error(`[reenviar-email] falha enviar ${email}:`, exc);
      return new Response(
        JSON.stringify({ ok: false, erro: "Falha temporária no envio. Tente em alguns minutos." }),
        { status: 500, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
      );
    }
  } else {
    console.log(`[reenviar-email] email não-ativo ignorado: ${email}`);
    // Pausa pequena pra timing não revelar diferença
    await new Promise((r) => setTimeout(r, 400));
  }

  return new Response(
    JSON.stringify({
      ok: true,
      mensagem: "Se este e-mail tem uma assinatura ativa, você receberá o link em até 5 minutos. Confira também o spam.",
    }),
    { status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
  );
});
