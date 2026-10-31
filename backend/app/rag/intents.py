import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFD', str(text).lower().replace('đ', 'd'))
    return re.sub(r'\s+', ' ', ''.join(c for c in text if unicodedata.category(c) != 'Mn')).strip()


def user_messages(history):
    return [m.get('message') or m.get('content') or '' for m in (history or [])
            if m.get('sender', m.get('role')) == 'user']


def damage_description(query):
    text = normalize(query)
    text = re.sub(r'nhiet do (?:bi )?(?:roi|rot|giam)', '', text)
    # A denial is not an admission of accidental damage.
    text = re.sub(r'(?:khong|chua|chua tung|khong he)(?: bi| lam| de)? (?:roi|rot|va dap|va cham|vo|nut)(?: vo)?', '', text)
    cases = [
        (r'\b(?:roi|rot|va dap|va cham|nut vo|bi vo|nut gay|mop meo)\b', 'rơi/rớt hoặc va đập', 'physical'),
        (r'\b(?:ngam nuoc|nuoc tran vao|do nuoc vao|nuoc vao bo|ngap nuoc)\b', 'nước xâm nhập', 'water'),
        (r'\b(?:tu thao|tu sua|sua ben ngoai|chuot can|set danh)\b', 'tác động bên ngoài hoặc tự sửa chữa', 'external'),
    ]
    for pattern, description, kind in cases:
        if re.search(pattern, text):
            return description, kind
    return None


def denies_damage(query):
    return bool(re.search(r'\b(?:khong|chua tung|chua|khong he)(?: bi| lam| de)? (?:roi|rot|va dap|va cham)\b', normalize(query)))


def prior_damage(history):
    for message in reversed(user_messages(history)):
        text = normalize(message)
        if denies_damage(message) or any(s in text for s in ('truong hop khac', 'may khac')):
            return None
        damage = damage_description(message)
        if damage:
            return damage
    return None


def is_temperature_question(query):
    text = normalize(query)
    return 'nhiet do' in text and any(s in text for s in ('khong', 'chinh', 'tang', 'giam', 'doi'))


def is_create_request_query(query):
    text = normalize(query)
    return bool(re.search(r'\b(?:tao|lam|lap|mo|gui|dang ky)\b.{0,35}\b(?:phieu|yeu cau bao hanh)\b', text))


def is_tracking_query(query, history=None):
    text = normalize(query)
    if is_create_request_query(query):
        return False
    if re.search(r'\bbh[-\s]\d{4}[-\s]\d+\b', text):
        return True
    if any(s in text for s in ('tien do', 'trang thai', 'phieu cua', 'phieu bao hanh', 'yeu cau cua',
                               'phieu nao', 'phieu do', 'phieu nay', 'cac phieu', 'tat ca phieu', 'xem phieu', 'bao nhieu phieu',
                               'xong chua', 'den dau', 'lich hen', 'ky thuat vien', 'ai sua',
                               'bao gio den', 'khi nao den', 'khi nao sua', 'da sua gi', 'ket qua sua', 'bien ban', 'ly do tu choi')):
        return True
    followup = any(s in text for s in ('khi nao', 'bao gio', 'ly do', 'vi sao', 'tai sao', 'con cai nao', 'con phieu', 'xem tiep'))
    return followup and any(is_tracking_query(m) for m in user_messages(history)[-4:])


def search_query(query, history=None):
    text = normalize(query)
    damage = damage_description(query) or (None if denies_damage(query) else prior_damage(history))
    if damage:
        text += {'physical': ' roi vo va dap tac dong vat ly tu choi bao hanh',
                 'water': ' ngam nuoc am uot tu choi bao hanh',
                 'external': ' tu sua chua tac dong ben ngoai tu choi bao hanh'}[damage[1]]
    if is_temperature_question(query):
        text += ' dieu kien bao hanh loi ky thuat nha san xuat'
    return text
