"""
Gera os assets de identidade do app a partir do PNG oficial da Iter.

Fonte oficial: C:\\Dev\\Iter\\Icon Iter.png — fornecido pelo brand manager.
A composição é o "icon mark" Iter: dot azul sólido (#2b6bff) + stem off-white,
sobre fundo preto puro (com leve glow azul ao redor do dot que faz parte da
arte original).

Saídas:
  app/assets/iter-icon-source.png  — cópia versionada do PNG oficial
  app/assets/icon.ico              — multi-res 16/32/48/64/128/256 (Windows)
  app/assets/iter-logo-ui.png      — versão com fundo transparente para uso
                                     em headers da UI (preto puro -> alpha 0)
  app/assets/iter-logo-ui-64.png   — versão 64x64 pré-escalada para Flet
  app/assets/iter-wordmark.png     — wordmark completo "iTER" (i oficial +
                                     "TER" em Segoe UI Black off-white)
                                     fundo transparente, para uso no onboarding
                                     e rodapé das demais telas

Rodar: `python app/assets/gen_icon.py`
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTE_OFICIAL = Path(r"C:\Dev\Iter\Icon Iter.png")
WORDMARK_OFICIAL = Path(r"C:\Dev\Iter\Wordmark.png")
FONT_CANDIDATES_HEAVY = [
    r"C:\Windows\Fonts\segoeuiz.ttf",   # Segoe UI Black (peso 900)
    r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold (fallback)
    r"C:\Windows\Fonts\ariblk.ttf",     # Arial Black (fallback de último caso)
]
COR_FG_BRAND = (245, 236, 216, 255)     # #f5ecd8 off-white quente

# Threshold para identificar o "fundo preto" (luminância < esse valor -> alpha 0)
THRESHOLD_PRETO = 12

# Limiares para extrair só os elementos sólidos da marca (dot azul + texto/stem
# branco), descartando o glow halo azul que aparece nos PNGs oficiais.
BLUE_DOT_MIN_B  = 200   # B >= 200 → pixel é parte do dot sólido (ou anti-alias)
WHITE_MIN_RGB   = 200   # min(R,G,B) >= 200 → pixel é parte do texto/stem branco


def _carregar_oficial() -> Image.Image:
    if not FONTE_OFICIAL.exists():
        raise FileNotFoundError(
            f"Asset oficial não encontrado em {FONTE_OFICIAL}. "
            "Conferir se o brand kit está montado no caminho esperado."
        )
    return Image.open(FONTE_OFICIAL).convert("RGBA")


def _remover_fundo_preto(im: Image.Image, threshold: int = THRESHOLD_PRETO) -> Image.Image:
    """
    Torna transparente todo pixel cuja luminância está abaixo do threshold.
    Mantém o stem branco e o dot azul intactos — só apaga o "preto canvas".
    Usado pra preparar o .ico (que mantém fundo preto opaco depois).
    """
    out = im.copy()
    pixels = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            lum = (r * 0.299 + g * 0.587 + b * 0.114)
            if lum < threshold:
                pixels[x, y] = (0, 0, 0, 0)
    return out


def _limpar_glow(im: Image.Image) -> Image.Image:
    """
    Mantém SOMENTE o dot azul sólido e o texto/stem branco; remove o glow
    halo azul que rodeia o dot nos PNGs oficiais. Tudo o que não é dot
    sólido nem texto branco fica transparente.

    Regra de keep (por pixel):
      - B >= 200                  → faz parte do dot azul (inclui anti-alias)
      - min(R,G,B) >= 200         → faz parte do texto/stem branco
      - Tudo o mais (glow halo, fundo) → alpha 0
    """
    out = im.copy()
    pixels = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, _a = pixels[x, y]
            is_dot = b >= BLUE_DOT_MIN_B
            is_white = min(r, g, b) >= WHITE_MIN_RGB
            if is_dot or is_white:
                pixels[x, y] = (r, g, b, 255)
            else:
                pixels[x, y] = (0, 0, 0, 0)
    return out


def _carregar_fonte_heavy(altura_px: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES_HEAVY:
        if Path(path).exists():
            return ImageFont.truetype(path, size=altura_px)
    return ImageFont.load_default()


def _gerar_wordmark(i_transparente: Image.Image, destino: Path) -> None:
    """
    Compõe o wordmark "iTER" usando o "i" oficial (transparente) + "TER" em
    Segoe UI Black off-white. A altura do TER iguala o "stem visível" do i
    para alinhamento tipográfico.
    """
    iw, ih = i_transparente.size

    # Tamanho da fonte: tem que ser o suficiente para "TER" ter cap-height ≈ altura
    # útil do i (do topo do dot até a base do stem). Como o glow azul faz a imagem
    # ficar mais alta que o stem, usamos ~78% da altura como cap-height alvo.
    cap_height_alvo = int(ih * 0.66)
    # Em Segoe UI Black, cap-height ≈ 0.72 do em-size, então:
    font_size = int(cap_height_alvo / 0.72)
    fonte = _carregar_fonte_heavy(font_size)

    # Mede "TER"
    bbox_ter = fonte.getbbox("TER")
    ter_w = bbox_ter[2] - bbox_ter[0]
    ter_h = bbox_ter[3] - bbox_ter[1]

    # Pad horizontal entre o "i" e o "T"
    pad_x = int(font_size * 0.06)

    # Canvas final: largura = i + pad + TER, altura = max(i, TER) com margem
    margem = int(font_size * 0.08)
    canvas_w = iw + pad_x + ter_w + margem * 2
    canvas_h = ih + margem * 2
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Cola o "i" alinhado à esquerda
    canvas.alpha_composite(i_transparente, (margem, margem))

    # Desenha "TER" alinhado à direita do i, baseline alinhada com a base do stem
    # do i. O stem do "i" termina próximo da base da imagem; alinhamos o baseline
    # do texto pela base do glyph TER, que cai em bbox_ter[3] do ponto de
    # desenho. Queremos baseline ≈ base da imagem do i (margem + ih).
    draw = ImageDraw.Draw(canvas)
    x_text = margem + iw + pad_x - bbox_ter[0]
    y_text = (margem + ih) - bbox_ter[3]  # alinhar base do TER com base do i
    draw.text((x_text, y_text), "TER", font=fonte, fill=COR_FG_BRAND)

    # Trim para cortar transparente excedente nas bordas
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)

    canvas.save(destino, format="PNG")


def _gerar_ico(im_fundo_preto: Image.Image, destino: Path) -> None:
    """
    Salva .ico multi-res a partir da imagem original (com fundo preto).
    O fundo preto é mantido no .ico — Windows mostra o ícone melhor com
    fundo opaco quando exibido em barras claras.
    """
    sizes = [16, 32, 48, 64, 128, 256]
    base = im_fundo_preto.copy()
    # Garante quadrado (a fonte é 231x235; pad para quadrado preto)
    w, h = base.size
    lado = max(w, h)
    quadrado = Image.new("RGBA", (lado, lado), (0, 0, 0, 255))
    quadrado.paste(base, ((lado - w) // 2, (lado - h) // 2), base)

    # Pre-escala para cada tamanho com LANCZOS
    imagens = [quadrado.resize((s, s), Image.LANCZOS) for s in sizes]
    imagens[-1].save(  # maior primeiro
        destino,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=imagens[:-1],
    )


def main() -> None:
    out_dir = Path(__file__).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    oficial = _carregar_oficial()
    print(f"Fonte: {FONTE_OFICIAL} ({oficial.size}, {oficial.mode})")

    # 1) Cópia versionada do oficial
    copia = out_dir / "iter-icon-source.png"
    oficial.save(copia, format="PNG")
    print(f"  cópia oficial -> {copia}")

    # 2) Versão "limpa" do icon mark: só dot sólido + stem branco, sem glow halo.
    #    Usada tanto pelo icon.ico (composto sobre fundo preto pro Windows)
    #    quanto pelo iter-logo-ui.png (transparente pra uso na UI).
    icon_limpo = _limpar_glow(oficial)
    bbox_icon = icon_limpo.getbbox()
    if bbox_icon:
        icon_limpo_crop = icon_limpo.crop(bbox_icon)
    else:
        icon_limpo_crop = icon_limpo

    # 3) icon.ico multi-res — compõe o icon limpo sobre fundo preto opaco
    #    pra o Windows mostrar bem mesmo em barras claras.
    ico_fonte = Image.new("RGBA", oficial.size, (0, 0, 0, 255))
    # Centraliza o icon_limpo (após crop) no canvas do tamanho original
    if bbox_icon:
        cx = (oficial.size[0] - icon_limpo_crop.size[0]) // 2
        cy = (oficial.size[1] - icon_limpo_crop.size[1]) // 2
        ico_fonte.alpha_composite(icon_limpo_crop, (cx, cy))
    else:
        ico_fonte = icon_limpo

    ico_path = out_dir / "icon.ico"
    _gerar_ico(ico_fonte, ico_path)
    print(f"  icon.ico (sem glow) -> {ico_path}")

    # 4) Versão transparente do icon mark para UI (sem glow)
    ui_path = out_dir / "iter-logo-ui.png"
    icon_limpo_crop.save(ui_path, format="PNG")
    print(f"  iter-logo-ui.png (sem glow) -> {ui_path} ({icon_limpo_crop.size})")

    # 5) Versão 64x64 pré-escalada
    h_ui = 64
    razao = h_ui / icon_limpo_crop.size[1]
    w_ui = int(icon_limpo_crop.size[0] * razao)
    pequeno = icon_limpo_crop.resize((w_ui, h_ui), Image.LANCZOS)
    ui64_path = out_dir / "iter-logo-ui-64.png"
    pequeno.save(ui64_path, format="PNG")
    print(f"  iter-logo-ui-64.png (sem glow) -> {ui64_path} ({pequeno.size})")

    # 6) Wordmark "iTER" — usa o asset oficial fornecido pelo brand manager
    #    (C:\Dev\Iter\Wordmark.png), aplica _limpar_glow pra remover o halo
    #    azul que rodeia o dot. Resultado: só letras "TER", stem do "i" e
    #    bolinha azul sólida. Fundo + glow viram transparentes.
    wordmark_path = out_dir / "iter-wordmark.png"
    if WORDMARK_OFICIAL.exists():
        wm_oficial = Image.open(WORDMARK_OFICIAL).convert("RGBA")
        wm_limpo = _limpar_glow(wm_oficial)
        bbox = wm_limpo.getbbox()
        if bbox:
            wm_limpo = wm_limpo.crop(bbox)
        wm_limpo.save(wordmark_path, format="PNG")
        print(f"  iter-wordmark.png (oficial, sem glow) -> {wordmark_path} ({wm_limpo.size})")
    else:
        # Fallback: gera programaticamente caso o asset oficial não esteja disponível
        _gerar_wordmark(icon_limpo_crop, wordmark_path)
        wm = Image.open(wordmark_path)
        print(f"  iter-wordmark.png (gerado, fallback) -> {wordmark_path} ({wm.size})")


if __name__ == "__main__":
    main()
