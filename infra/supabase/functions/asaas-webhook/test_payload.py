"""
Script de teste local da Edge Function asaas-webhook.

Envia um payload sintético (formato real do Asaas) pra um endpoint local ou
remoto. Útil pra testar a Edge Function sem precisar do Asaas real.

USO LOCAL (Supabase CLI rodando):
  1. Em outro terminal: supabase functions serve asaas-webhook --env-file infra/supabase/functions/asaas-webhook/.env.local
  2. python infra/supabase/functions/asaas-webhook/test_payload.py confirmed teste@email.com

USO REMOTO (após deploy):
  python infra/supabase/functions/asaas-webhook/test_payload.py confirmed teste@email.com \\
      --url https://YOUR-PROJECT.supabase.co/functions/v1/asaas-webhook \\
      --token SEU_ASAAS_WEBHOOK_TOKEN

Cenários disponíveis:
  confirmed     PAYMENT_CONFIRMED       (ativa usuário, valid_until=nextDue+7d)
  received      PAYMENT_RECEIVED        (mesmo efeito que confirmed)
  overdue       PAYMENT_OVERDUE         (desativa usuário, atrasado)
  cancelled     SUBSCRIPTION_INACTIVATED (desativa)
  sub_created   SUBSCRIPTION_CREATED    (registra mas não ativa)
  unknown       ALGO_DESCONHECIDO       (deve responder 200 ignorado)

Nota: o customer_id no payload é fixo (cus_test_001). A função vai chamar
a API Asaas pra buscar o e-mail desse customer — então em sandbox você
PRECISA ter um customer real com esse ID OU adaptar o script pra usar um ID
do seu sandbox.
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta


def _payload(evento_asaas: str, customer_id: str) -> dict:
    """Monta payload no formato real do webhook Asaas."""
    agora = datetime.utcnow()
    next_due = (agora + timedelta(days=30)).strftime("%d/%m/%Y")

    base = {
        "id": f"evt_test_{int(agora.timestamp())}",
        "event": evento_asaas,
        "dateCreated": agora.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if evento_asaas.startswith("PAYMENT_"):
        base["payment"] = {
            "object": "payment",
            "id": "pay_test_001",
            "customer": customer_id,
            "subscription": "sub_test_001",
            "value": 9.90,
            "netValue": 9.75,
            "billingType": "PIX",
            "dueDate": (agora + timedelta(days=30)).strftime("%Y-%m-%d"),
            "status": (
                "CONFIRMED" if evento_asaas == "PAYMENT_CONFIRMED"
                else "RECEIVED" if evento_asaas == "PAYMENT_RECEIVED"
                else "OVERDUE" if evento_asaas == "PAYMENT_OVERDUE"
                else "PENDING"
            ),
        }
    elif evento_asaas.startswith("SUBSCRIPTION_"):
        base["subscription"] = {
            "object": "subscription",
            "id": "sub_test_001",
            "customer": customer_id,
            "value": 9.90,
            "cycle": "MONTHLY",
            "billingType": "PIX",
            "nextDueDate": next_due,
            "status": "ACTIVE" if "CREATED" in evento_asaas else "INACTIVE",
        }
    return base


CENARIOS = {
    "confirmed":   "PAYMENT_CONFIRMED",
    "received":    "PAYMENT_RECEIVED",
    "overdue":     "PAYMENT_OVERDUE",
    "cancelled":   "SUBSCRIPTION_INACTIVATED",
    "sub_created": "SUBSCRIPTION_CREATED",
    "unknown":     "ALGO_DESCONHECIDO",
}


def main() -> int:
    p = argparse.ArgumentParser(description="Test webhook Asaas localmente.")
    p.add_argument("cenario", choices=sorted(CENARIOS), help="cenário de teste")
    p.add_argument("email", help="e-mail do cliente alvo (ignorado pelo Asaas API se rodando contra mock)")
    p.add_argument("--customer-id", default="cus_test_001",
                   help="ID do customer no Asaas (default: cus_test_001)")
    p.add_argument("--url", default="http://localhost:54321/functions/v1/asaas-webhook",
                   help="endpoint da Edge Function (local default)")
    p.add_argument("--token", default="qualquer-coisa-aleatoria-32-chars",
                   help="valor do header asaas-access-token (default = placeholder do tutorial)")
    args = p.parse_args()

    evento = CENARIOS[args.cenario]
    body = _payload(evento, args.customer_id)
    body_json = json.dumps(body).encode("utf-8")

    print(f">> POST {args.url}")
    print(f">> evento: {evento}")
    print(f">> body  : {json.dumps(body, indent=2, ensure_ascii=False)}")

    req = urllib.request.Request(
        args.url,
        data=body_json,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "asaas-access-token": args.token,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            corpo = resp.read().decode("utf-8")
        print(f"\n<< {status}")
        print(f"<< {corpo}")
        return 0 if status == 200 else 1
    except urllib.error.HTTPError as e:
        print(f"\n<< {e.code}")
        print(f"<< {e.read().decode('utf-8', errors='replace')}")
        return 1
    except Exception as exc:
        print(f"\n!! erro: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
