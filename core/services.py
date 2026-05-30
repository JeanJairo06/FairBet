PESOS = (3, 2, 7, 6, 5, 4, 3, 2)
SERIE_NUMERICA = (6, 7, 8, 9, 0, 1, 1, 2, 3, 4, 5)
SERIE_LETRA = ('K', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J')


def calcular_digito_verificador(dni_8):
    dni_8 = str(dni_8).strip()
    if len(dni_8) != 8 or not dni_8.isdigit():
        raise ValueError('Se requieren exactamente 8 digitos numericos.')
    suma = sum(int(d) * p for d, p in zip(dni_8, PESOS))
    indice = 11 - (suma % 11)
    if indice == 11:
        indice = 0
    return SERIE_NUMERICA[indice]


def digito_verificador_letra(dni_8):
    dni_8 = str(dni_8).strip()
    if len(dni_8) != 8 or not dni_8.isdigit():
        raise ValueError('Se requieren exactamente 8 digitos numericos.')
    suma = sum(int(d) * p for d, p in zip(dni_8, PESOS))
    indice = 11 - (suma % 11)
    if indice == 11:
        indice = 0
    return SERIE_LETRA[indice]


def validar_dni_peruano(dni):
    dni = dni.strip().upper()
    if len(dni) == 8:
        if not dni.isdigit():
            return False
        if dni == '0' * 8:
            return False
        return True
    if len(dni) == 9:
        if not dni[:8].isdigit():
            return False
        if dni[:8] == '0' * 8:
            return False
        verificador_num = calcular_digito_verificador(dni[:8])
        verificador_let = digito_verificador_letra(dni[:8])
        actual = dni[8]
        return actual == str(verificador_num) or actual == verificador_let
    return False
