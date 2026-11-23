"""Composición de reportes A4 con encabezados, tablas que continúan y páginas numeradas."""

import io
import re
import threading
from pathlib import Path
from xml.sax.saxutils import escape  # nosec B406 # solo se importa escape para texto PDF; no se analiza XML externo

_font_lock = threading.Lock()


def build_reporte(data):
    """Construye en memoria el PDF con las secciones de datos recibidas, tablas paginadas y encabezados comunes."""
    datos = data
    try:
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
    except ImportError as excepcion:
        raise ValueError("Falta ReportLab. Instala las dependencias siguiendo el README del proyecto.") from excepcion
    with _font_lock:
        if 'Hemeroteca' not in pdfmetrics.getRegisteredFontNames():
            folder = Path(reportlab.__file__).parent / 'fonts'
            pdfmetrics.registerFont(TTFont('Hemeroteca', str(folder / 'Vera.ttf')))
            pdfmetrics.registerFont(TTFont('HemerotecaBold', str(folder / 'VeraBd.ttf')))
    blue, ink, gray = colors.HexColor('#284B9B'), colors.HexColor('#20304C'), colors.HexColor('#64748B')
    cuerpo = ParagraphStyle('body', fontName='Hemeroteca', fontSize=8, leading=11, textColor=ink,
                          alignment=TA_LEFT, splitLongWords=True)
    small = ParagraphStyle('small', parent=cuerpo, fontSize=7, leading=9)
    encabezado = ParagraphStyle('heading', parent=cuerpo, fontName='HemerotecaBold', fontSize=18, leading=23, spaceAfter=10, textColor=blue)
    subheading = ParagraphStyle('subheading', parent=encabezado, fontSize=12, leading=16, spaceAfter=8)
    header_style = ParagraphStyle('tableheader', parent=small, fontName='HemerotecaBold', textColor=colors.white)

    def parrafo(value, style=small):
        """Escapa texto para ReportLab, retira controles no imprimibles y conserva los saltos de línea visibles."""
        valor = value
        valor = '-' if valor is None or valor == '' else str(valor)
        valor = re.sub(r'[\x00-\x08\x0b-\x1f]', '', valor)
        return Paragraph(escape(valor).replace('\n', '<br/>'), style)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    paragraph = parrafo

    flujo = io.BytesIO()
    ancho, alto = landscape(A4)
    margin = 35
    usable = ancho - margin * 2
    documento = SimpleDocTemplate(flujo, pagesize=(ancho, alto), rightMargin=margin, leftMargin=margin,
                                 topMargin=60, bottomMargin=44, pageCompression=1,
                                 title='Hemeroteca - Reporte de ejemplares' if datos['scope'] == 'issues' else 'Hemeroteca - Reporte general',
                                 author=datos['generated_by'])
    contenido_documento = [paragraph('Reporte de ejemplares' if datos['scope'] == 'issues' else 'Reporte general de Hemeroteca', encabezado),
             paragraph(f"Emitido: {datos['generated_at']} (UTC)\nPor: {datos['generated_by']}", cuerpo), Spacer(1, 10)]
    if datos['scope'] == 'issues':
        etiquetas = {'title': 'Periódico', 'kind': 'Tipo', 'year': 'Año', 'month': 'Mes', 'day': 'Día',
                     'period': 'Periodo de registro', 'desde': 'Desde', 'hasta': 'Hasta'}
        seleccionado = [f'{etiquetas[clave]}: {valor}' for clave, valor in datos['filters'].items() if valor is not None]
        contenido_documento += [paragraph('Filtros: ' + ('; '.join(seleccionado) if seleccionado else 'Todos los ejemplares activos'), cuerpo),
                  paragraph('Incluye todas las páginas del resultado. Orden: registro más reciente primero.', cuerpo), Spacer(1, 14)]
    else:
        contenido_documento += [paragraph('Contenido operativo completo: inventario, fechas sin publicación, cuentas, permisos, solicitudes, auditoría y computadoras autorizadas.', cuerpo),
                  paragraph('Este PDF sirve para consulta. Para restaurar el sistema utiliza un archivo .hmbackup. Las credenciales, respuestas de seguridad, códigos, sesiones y claves técnicas se excluyen del reporte.', cuerpo), Spacer(1, 14)]

    def publicacion(row):
        """Presenta la fecha del ejemplar en formato día/mes/año con dos dígitos para día y mes."""
        fila = row
        return f"{fila['day']:02d}/{fila['month']:02d}/{fila['year']}"
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    publication = publicacion

    for indice, section in enumerate(datos['sections']):
        if indice:
            contenido_documento.append(PageBreak())
        filas = section['rows']
        contenido_documento += [paragraph(section['title'], subheading), paragraph(f'{len(filas)} registros', cuerpo), Spacer(1, 8)]
        if not filas:
            contenido_documento.append(paragraph('No hay registros en esta sección.', cuerpo))
            continue
        tipo = section['type']
        if tipo == 'issues':
            columnas, tamanos = ['Periódico / tipo', 'Publicación', 'Edición / número', 'Ubicación', 'Estado', 'Registro'], [21, 11, 16, 14, 14, 24]
            celdas = [[f"{registro_breve['title']}\n{registro_breve['kind']}", publication(registro_breve), f"{registro_breve['edition'] or '-'}\nN.º {registro_breve['number'] or '-'}",
                      f"Estante: {registro_breve['shelf'] or '-'}\nGaveta: {registro_breve['drawer'] or '-'}", registro_breve['status'],
                      f"#{registro_breve['id']}\n{registro_breve['created_at']}\n{registro_breve['created_by']}"] for registro_breve in filas]
        elif tipo == 'absent':
            columnas, tamanos = ['Periódico', 'Publicación', 'Observación', 'Registro'], [25, 13, 36, 26]
            celdas = [[f"{registro_breve['title']}\n{registro_breve['kind']}", publication(registro_breve), registro_breve['note'], f"#{registro_breve['id']}\n{registro_breve['created_at']}\n{registro_breve['created_by']}"] for registro_breve in filas]
        elif tipo == 'users':
            columnas, tamanos = ['Persona', 'Documento', 'Perfil', 'Estado', 'Registro'], [24, 21, 22, 11, 22]
            celdas = [[registro_breve['name'], registro_breve['document'], registro_breve['role'], 'Activo' if registro_breve['active'] else 'Inactivo', f"#{registro_breve['id']}\n{registro_breve['created_at']}"] for registro_breve in filas]
        elif tipo == 'grants':
            columnas, tamanos = ['Persona', 'Documento', 'Permiso aprobado'], [30, 25, 45]
            celdas = [[registro_breve['name'], registro_breve['document'], registro_breve['permission']] for registro_breve in filas]
        elif tipo == 'requests':
            columnas, tamanos = ['Solicitud / persona', 'Permiso / motivo', 'Decisión / respuesta'], [28, 37, 35]
            celdas = [[f"#{registro_breve['id']} - {registro_breve['created_at']}\n{registro_breve['name']}\n{registro_breve['document']}", f"{registro_breve['permission']}\n{registro_breve['reason']}",
                      f"{registro_breve['status']}\n{registro_breve['decided_by'] or '-'}\n{registro_breve['decided_at'] or '-'}\n{registro_breve['response'] or '-'}"] for registro_breve in filas]
        elif tipo == 'audit':
            columnas, tamanos = ['Fecha / registro', 'Persona', 'Acción', 'Resultado'], [18, 23, 44, 15]
            celdas = [[f"#{registro_breve['id']}\n{registro_breve['at']}", registro_breve['user'], registro_breve['action'], registro_breve['result']] for registro_breve in filas]
        elif tipo == 'devices':
            columnas, tamanos = ['Computadora', 'Acceso', 'Autorizada por', 'Fecha'], [28, 14, 34, 24]
            celdas = [[registro_breve['name'], 'Activo' if registro_breve['active'] else 'Retirado', registro_breve['approved_by'], registro_breve['approved_at']] for registro_breve in filas]
        else:
            raise ValueError('Sección de reporte desconocida.')
        tabla_datos = LongTable([[paragraph(elemento_breve, header_style) for elemento_breve in columnas]] + [[paragraph(elemento_breve) for elemento_breve in fila] for fila in celdas],
                          colWidths=[usable * tamano / 100 for tamano in tamanos], repeatRows=1, splitInRow=1, hAlign='LEFT')
        tabla_datos.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), blue), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F7FC')]),
            ('LINEBELOW', (0, 0), (-1, 0), .6, blue),
            ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#DDE5F0')),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
        contenido_documento.append(tabla_datos)

    def decorar(canvas, doc):
        """Dibuja el encabezado institucional y el número de página sin modificar el estado del lienzo del informe."""
        canvas.saveState()
        canvas.setFillColor(blue)
        canvas.setFont('HemerotecaBold', 11)
        canvas.drawString(margin, alto - 30, 'HEMEROTECA')
        canvas.setStrokeColor(colors.HexColor('#DDE5F0'))
        canvas.line(margin, alto - 40, ancho - margin, alto - 40)
        canvas.setFillColor(gray)
        canvas.setFont('Hemeroteca', 7)
        canvas.drawString(margin, 24, 'Documento de consulta - Datos al momento de la emisión')
        canvas.drawRightString(ancho - margin, 24, f'Página {doc.page}')
        canvas.restoreState()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    decorate = decorar

    documento.build(contenido_documento, onFirstPage=decorate, onLaterPages=decorate)
    return flujo.getvalue()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
build_report = build_reporte
