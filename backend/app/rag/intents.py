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


# Bug 1: prompt-injection / role-play attempts are refused with the default scope reply.
JAILBREAK_PATTERNS = (
    r'\b(?:bo qua|phot lo|khong can tuan theo|vuot qua)\b.{0,30}\b(?:huong dan|chi dan|chi thi|quy tac|luat|lenh|cau hinh|prompt|gioi han)\b',
    r'\bignore\b.{0,30}\b(?:instruction|rule|prompt|previous|above)s?\b',
    r'\b(?:system prompt|developer mode|jailbreak|dan mode|do anything now|prompt goc|prompt he thong)\b',
    r'\b(?:dong vai|gia vo la|gia lam|hay tro thanh|tu bay gio ban la|you are now|act as|pretend)\b',
    r'\b(?:tiet lo|in ra|cho xem|hien thi)\b.{0,25}\b(?:prompt|chi dan he thong|quy tac cua ban|cau hinh|api key|mat khau)\b',
    r'\b(?:phieu|thong tin|so dien thoai|du lieu)\b.{0,20}\b(?:cua )?(?:khach hang khac|nguoi khac|tat ca khach)\b',
)

# Bug 1: topics clearly unrelated to warranty support.
OFF_TOPIC = (
    'thoi tiet', 'bong da', 'tran dau', 'chinh tri', 'bau cu', 'tong thong', 'chung khoan', 'co phieu', 'bitcoin',
    'tien ao', 'xo so', 'lo de', 'ca do', 'nau an', 'cong thuc nau', 'mon an', 'cong thuc lam', 'lam tho', 'bai tho',
    'viet tho', 'bai hat', 'loi bai hat', 'ke chuyen', 'truyen cuoi', 'phim', 'game', 'giai toan', 'bai tap', 'lam bai',
    'viet code', 'lap trinh', 'python', 'javascript', 'dich sang', 'dich cau', 'tieng anh la gi', 'tinh yeu', 'nguoi yeu',
    'tu vi', 'boi bai', 'horoscope', 'du lich', 'dat ve', 'khach san', 'thu do', 'lich su', 'dia ly',
    'bac si', 'hack', 'virus may tinh', 'vay tien', 'kiem tien',
)
DOMAIN_TERMS = (
    'bao hanh', 'phieu', 'san pham', 'thiet bi', 'may', 'tivi', 'tu lanh', 'dieu hoa', 'quat', 'noi', 'lo vi song',
    'loi', 'hong', 'hu', 'sua', 'ky thuat', 'linh kien', 'chinh sach', 'nhan vien', 'cskh', 'hotline', 'tong dai',
    'model', 'serial', 'remote', 'dieu khien', 'nguon', 'man hinh', 'lanh', 'nong', 'keu', 'chay', 'tat', 'bat',
)


def is_jailbreak(query):
    text = normalize(query)
    return any(re.search(p, text) for p in JAILBREAK_PATTERNS)


def is_out_of_scope(query):
    text = normalize(query)
    if is_jailbreak(query):
        return True
    if not any(re.search(rf'\b{re.escape(t)}\b', text) for t in OFF_TOPIC):
        return False
    return not any(re.search(rf'\b{re.escape(t)}\b', text) for t in DOMAIN_TERMS)


# Bug 2: customer asks to talk to a human.
def is_contact_staff_query(query):
    text = normalize(query)
    return bool(re.search(
        r'\b(?:lien he|lien lac|goi|gap|noi chuyen|ket noi|chuyen sang|chuyen cho|xin so)\b.{0,20}'
        r'\b(?:nhan vien|nguoi that|tu van vien|cskh|cham soc khach hang|tong dai|hotline|nguoi ho tro|quan ly)\b', text)
        or re.search(r'\b(?:so hotline|so tong dai|so dien thoai (?:cskh|ho tro|bao hanh)|hotline la|tong dai la)\b', text))
