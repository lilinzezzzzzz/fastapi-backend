def extract_dict(d, keys):
    return {k: v for k, v in d.items() if k in keys}
