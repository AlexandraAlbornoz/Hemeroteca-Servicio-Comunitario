"""Dibuja el icono vectorial de periódico y exporta recursos nativos de Windows."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def fuente(tamano, negrita=False):
    """Carga una fuente de Windows y ofrece una alternativa para otras plataformas."""
    ruta = Path('C:/Windows/Fonts') / ('segoeuib.ttf' if negrita else 'segoeui.ttf')
    return ImageFont.truetype(str(ruta), tamano) if ruta.exists() else ImageFont.load_default(size=tamano)


def dibujar_periodico(tamano=512):
    """Representa un periódico plegado con titular, fotografía y columnas de texto."""
    imagen = Image.new('RGBA', (512, 512))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rounded_rectangle((12, 12, 500, 500), radius=108, fill='#244C91')
    dibujo.rounded_rectangle((108, 109, 426, 423), radius=27, fill='#14386E')
    dibujo.rounded_rectangle((83, 87, 395, 412), radius=22, fill='#F7FAFF')
    dibujo.rounded_rectangle((365, 149, 427, 412), radius=22, fill='#C7D7EC')
    dibujo.rectangle((365, 149, 395, 390), fill='#C7D7EC')
    dibujo.rounded_rectangle((365, 149, 395, 389), radius=13, fill='#E1EAF5')
    dibujo.rounded_rectangle((110, 115, 345, 175), radius=8, fill='#244C91')
    dibujo.text((126, 112), 'PRENSA', font=fuente(48, True), fill='white')
    dibujo.rounded_rectangle((110, 192, 345, 203), radius=4, fill='#CB8151')
    dibujo.rounded_rectangle((110, 224, 207, 308), radius=8, fill='#91AED4')
    dibujo.polygon([(115, 299), (145, 260), (166, 281), (188, 251), (202, 299)], fill='#244C91')
    dibujo.ellipse((122, 235, 139, 252), fill='#F7FAFF')
    for posicion in (227, 251, 275, 299):
        dibujo.rounded_rectangle((224, posicion, 344, posicion + 8), radius=3, fill='#647A97')
    for posicion in (331, 353, 375):
        dibujo.rounded_rectangle((110, posicion, 344, posicion + 8), radius=3, fill='#647A97')
    return imagen.resize((tamano, tamano), Image.Resampling.LANCZOS)


def principal():
    """Genera ICO multirresolución, PNG, SVG y la ilustración del asistente."""
    raiz = Path(__file__).resolve().parents[2]
    recursos = raiz / 'assets'
    recursos.mkdir(exist_ok=True)
    imagen = dibujar_periodico()
    imagen.save(recursos / 'hemeroteca_periodico.ico', sizes=[(medida, medida) for medida in (16, 24, 32, 48, 64, 128, 256)])
    imagen.resize((256, 256), Image.Resampling.LANCZOS).save(recursos / 'hemeroteca_periodico.png')
    vector = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect x="12" y="12" width="488" height="488" rx="108" fill="#244c91"/><rect x="83" y="87" width="312" height="325" rx="22" fill="#f7faff"/><rect x="365" y="149" width="62" height="263" rx="22" fill="#c7d7ec"/><rect x="110" y="115" width="235" height="60" rx="8" fill="#244c91"/><text x="126" y="160" font-family="Segoe UI,sans-serif" font-size="48" font-weight="700" fill="white">PRENSA</text><path d="M110 197H345" stroke="#cb8151" stroke-width="11"/><rect x="110" y="224" width="97" height="84" rx="8" fill="#91aed4"/><path d="M224 231H344M224 255H344M224 279H344M224 303H344M110 335H344M110 357H344M110 379H344" stroke="#647a97" stroke-width="8"/></svg>'''
    (recursos / 'hemeroteca_periodico.svg').write_text(vector, encoding='utf-8')
    lateral = Image.new('RGB', (164, 314), '#244C91')
    lateral.paste(dibujar_periodico(120), (22, 32), dibujar_periodico(120))
    dibujo = ImageDraw.Draw(lateral)
    dibujo.text((12, 181), 'HEMEROTECA', font=fuente(19, True), fill='white')
    dibujo.text((20, 212), 'Prensa histórica', font=fuente(14, True), fill='white')
    dibujo.text((20, 262), 'Tu hemeroteca,', font=fuente(13), fill='#DCE8F7')
    dibujo.text((20, 281), 'siempre a mano.', font=fuente(13), fill='#DCE8F7')
    lateral.save(recursos / 'asistente_lateral.bmp')
    print('Iconos y recursos del asistente creados en', recursos)


if __name__ == '__main__':
    principal()
