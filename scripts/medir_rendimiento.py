"""Mide consultas paginadas sobre 10.000 ejemplares ficticios en una base temporal."""
import json
from pathlib import Path
import statistics
import tempfile
import time

from hemeroteca.config.settings import NATIONAL, SECURITY_QUESTIONS
from hemeroteca.services.container import create_services


def principal():
    """Comprueba resultados y un presupuesto local de dos segundos por consulta p95."""
    with tempfile.TemporaryDirectory(prefix='hemeroteca-perf-') as temporary:
        services = create_services(Path(temporary) / 'prueba.db')
        try:
            questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
            services.auth.create_master('Persona Ficticia', 'V-12345678', 'Prueba#2026', questions)
            actor = services.auth.authenticate('V-12345678', 'Prueba#2026')
            with services.connection:
                services.connection.executemany(
                    '''INSERT INTO issues(title,kind,edition,year,month,day,number,shelf,drawer,status,created_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    [(NATIONAL[0], 'Nacional', 'Matutina', 2020, 1, 1, str(index), '1', '', 'Disponible', 'Prueba', '2026-11-16T00:00:00Z') for index in range(10000)])
            times = []
            for index in range(25):
                started = time.perf_counter()
                result = services.periodicos.search_issues(actor, catalog=True, page=1 + index * 60)
                times.append(time.perf_counter() - started)
                if result['total'] != 10000 or len(result['items']) != 5:
                    raise RuntimeError('La consulta paginada no conserva los resultados esperados.')
            percentile = sorted(times)[23]
            print(json.dumps({'ejemplares': 10000, 'consultas': len(times), 'mediana_ms': round(statistics.median(times) * 1000, 3),
                              'p95_ms': round(percentile * 1000, 3), 'presupuesto_p95_ms': 2000}, indent=2))
            return 0 if percentile <= 2 else 1
        finally:
            services.close()


if __name__ == '__main__':
    raise SystemExit(principal())
