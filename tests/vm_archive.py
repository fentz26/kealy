"""Small newc encoder for disposable VM fixtures, not release images."""


def newc_entry(name, data, mode, inode):
    name = name.encode() + b'\0'
    fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0]
    result = b'070701' + b''.join(f'{value:08x}'.encode() for value in fields) + name
    result += b'\0' * (-len(result) % 4)
    result += data
    return result + b'\0' * (-len(result) % 4)


def append_newc(original, archive):
    # A gzip stream can end at any byte. The following raw newc archive cannot.
    return original + b'\0' * (-len(original) % 4) + archive
