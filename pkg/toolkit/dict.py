def extract_dict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def deep_compare_dict(d1: dict, d2: dict):
    if d1 is None and d2 is None:
        return True

    if d1 is None or d2 is None:
        return False

    if not (isinstance(d1, dict) and isinstance(d2, dict)):
        return False

    if d1.keys() != d2.keys():
        return False

    for key in d1:
        if isinstance(d1[key], dict) and isinstance(d2[key], dict):
            if not deep_compare_dict(d1[key], d2[key]):
                return False
        elif d1[key] != d2[key]:
            return False
    return True
