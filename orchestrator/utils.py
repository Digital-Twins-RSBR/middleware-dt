import re



def normalize_name(text):
    """
    Normaliza nomes para comparação semântica:
    - Troca separadores (_,-,.) por espaço
    - Separa letras e números (ex: AirConditioner1_77 -> AirConditioner 1 77)
    - Tudo minúsculo
    """
    if not text:
        return ''
    text = re.sub(r'[_.\-]', ' ', text)
    text = re.sub(r'([a-zA-Z])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()
    """
    Normaliza nomes para comparação semântica:
    - Troca separadores (_,-,.) por espaço
    - Separa letras e números (ex: AirConditioner1_77 -> AirConditioner 1 77)
    - Tudo minúsculo
    """
    if not text:
        return ''
    text = re.sub(r'[_.\-]', ' ', text)
    text = re.sub(r'([a-zA-Z])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()