"""Controles de filtros legibles para el historial de auditoría."""

import unicodedata
import customtkinter as ctk
from hemeroteca.ui.controles import SelectorCompacto


def usuario_auditoria_valido(texto):
    """Permite borrar, escribir nombres con tildes y separar palabras con espacios."""
    return all(caracter.isalpha() or caracter == ' ' for caracter in unicodedata.normalize('NFC', texto))


class SelectorHora(ctk.CTkFrame):
    """Selecciona una hora de 24 horas y minutos sin admitir escritura inválida."""

    def __init__(self, padre):
        """Construye dos listas compactas y una acción para quitar el filtro horario."""
        super().__init__(padre, fg_color='transparent')
        self.hora = SelectorCompacto(self, values=['Hora'] + [f'{valor:02d}' for valor in range(24)],
                                    state='readonly', width=90, command=self._elegir_hora)
        self.hora.pack(side='left')
        ctk.CTkLabel(self, text=':', width=18).pack(side='left')
        self.minuto = SelectorCompacto(self, values=['Min.'] + [f'{valor:02d}' for valor in range(60)],
                                      state='readonly', width=90, command=self._elegir_minuto)
        self.minuto.pack(side='left')
        ctk.CTkButton(self, text='Limpiar', width=70, command=self.delete).pack(side='left', padx=8)
        self._segundos_anteriores = ''
        self.delete()

    def _elegir_hora(self, valor):
        """Completa los minutos al elegir una hora y elimina precisión heredada."""
        self._segundos_anteriores = ''
        if valor == 'Hora':
            self.minuto.set('Min.')
        elif self.minuto.get() == 'Min.':
            self.minuto.set('00')

    def _elegir_minuto(self, valor):
        """Completa medianoche si se eligen los minutos antes que la hora."""
        self._segundos_anteriores = ''
        if valor != 'Min.' and self.hora.get() == 'Hora':
            self.hora.set('00')

    def get(self):
        """Devuelve el prefijo horario compatible con el servicio de auditoría."""
        if self.hora.get() == 'Hora':
            return ''
        if self.minuto.get() == 'Min.':
            return self.hora.get()
        return self.hora.get() + ':' + self.minuto.get() + self._segundos_anteriores

    def set(self, valor):
        """Restaura filtros previos, incluso su precisión de segundos, sin perder datos."""
        partes = valor.split(':') if valor else []
        if (len(partes) > 3 or any(not parte.isascii() or not parte.isdigit() or len(parte) > 2
                                  or int(parte) > limite for parte, limite in zip(partes, (23, 59, 59)))):
            raise ValueError('Hora inválida.')
        self.delete()
        if partes:
            self.hora.set(partes[0].zfill(2))
        if len(partes) >= 2:
            self.minuto.set(partes[1].zfill(2))
        if len(partes) == 3:
            self._segundos_anteriores = ':' + partes[2].zfill(2)

    def delete(self, *argumentos):
        """Quita el filtro y permite consultar eventos de cualquier hora."""
        self.hora.set('Hora')
        self.minuto.set('Min.')
        self._segundos_anteriores = ''
