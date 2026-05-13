import asyncio
import functools
from datetime import datetime, timedelta
from typing import Callable

from app.core.logger import get_logger

log = get_logger()


# ── Retry async ───────────────────────────────────────────────────────────────


def retry(vezes: int = 3, espera: float = 2.0, nao_retentar: tuple = ()):
    """Decorator async: tenta N vezes e relanca a excecao da ultima."""

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            ultimo_erro = None
            for tentativa in range(1, vezes + 1):
                try:
                    return await func(*args, **kwargs)
                except nao_retentar:
                    raise
                except Exception as exc:
                    ultimo_erro = exc
                    log.warning(
                        f"[{func.__name__}] tentativa {tentativa}/{vezes} falhou: {exc}"
                    )
                    if tentativa < vezes:
                        await asyncio.sleep(espera)
            raise ultimo_erro

        return wrapper

    return decorator


# ── Formatadores ──────────────────────────────────────────────────────────────

_EXCEL_EPOCH = datetime(1899, 12, 30)


def normalizar_data_br(valor) -> str:
    """
    Aceita datetime, date, string em varios formatos, ou serial Excel
    (numero de dias desde 1899-12-30) → retorna "DD/MM/YYYY".

    Tambem aceita inteiros de 7 ou 8 digitos no formato DDMMYYYY ou DMMYYYY
    — comum quando o usuario digita "13/05/2026" e o Excel converte para
    inteiro 13052026 (celula sem formato de data).
    """
    if valor is None:
        raise ValueError("data vazia")
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    s = str(valor).strip()
    if not s or s.lower() == "nan":
        raise ValueError("data vazia")

    # Branch novo: DDMMYYYY ou DMMYYYY (Excel comeu a barra)
    if s.isdigit() and len(s) in (7, 8):
        s_pad = s.zfill(8)
        try:
            return datetime.strptime(s_pad, "%d%m%Y").strftime("%d/%m/%Y")
        except ValueError:
            pass

    if "/" not in s and "-" not in s and ":" not in s:
        try:
            f = float(s)
            if 1.0 <= f <= 100_000.0:
                return (_EXCEL_EPOCH + timedelta(days=f)).strftime("%d/%m/%Y")
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    raise ValueError(f"Formato de data nao reconhecido: '{s}'")


def normalizar_hhmm(valor) -> str:
    """
    Aceita varios formatos de horas e retorna "HH:MM":
      - datetime.time(0, 30) — quando Excel grava celula como hora nativa
      - "01:30", "1:30"      — string HH:MM padrao
      - "01:30:00"           — string HH:MM:SS (Excel as vezes inclui segundos)
      - "0130"               — string compacta
      - "1.5"                — string decimal (horas)
      - 0.0625 (float)       — fracao do dia Excel (= 1h30min)
      - 1.5 (float)          — horas decimais

    Heuristica float: 0 < f < 1 → fracao do dia; f >= 1 → horas decimais.
    """
    if valor is None:
        raise ValueError("horas vazia")

    # Branch novo: datetime.time (tem hour/minute mas NAO tem year/month/day)
    if hasattr(valor, "hour") and hasattr(valor, "minute") and not hasattr(valor, "year"):
        return f"{valor.hour:02d}:{valor.minute:02d}"

    if isinstance(valor, str):
        s = valor.strip()
        if not s or s.lower() == "nan":
            raise ValueError("horas vazia")
        if ":" in s:
            partes = s.split(":")
            # Aceita HH:MM ou HH:MM:SS (Excel grava com segundos as vezes)
            if len(partes) not in (2, 3):
                raise ValueError(f"hh:mm invalido: '{s}'")
            try:
                h = int(partes[0])
                m = int(partes[1])
            except ValueError:
                raise ValueError(f"hh:mm com nao-numeros: '{s}'")
            if not (0 <= h <= 99 and 0 <= m <= 59):
                raise ValueError(f"hh:mm fora de faixa: '{s}'")
            return f"{h:02d}:{m:02d}"
        # Sem ":" — pode ser "0130" ou numero decimal
        if s.isdigit() and len(s) in (3, 4):
            h = int(s[:-2])
            m = int(s[-2:])
            if 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        try:
            valor = float(s.replace(",", "."))
        except ValueError:
            raise ValueError(f"horas em formato nao reconhecido: '{s}'")
    # Agora valor e numerico
    if isinstance(valor, (int, float)):
        f = float(valor)
        if 0 < f < 1:
            total_min = round(f * 24 * 60)
        else:
            total_min = round(f * 60)
        h, m = divmod(total_min, 60)
        return f"{h:02d}:{m:02d}"
    raise ValueError(f"tipo nao suportado para horas: {type(valor)}")


def normalizar_codigo(valor) -> str:
    """Remove sufixo .0 de numeros lidos como float pelo pandas e UPPER strip."""
    if valor is None:
        return ""
    s = str(valor).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def normalizar_icao(valor) -> str:
    """Codigo ICAO 4 chars uppercase, removendo sufixo .0."""
    return normalizar_codigo(valor).upper()
