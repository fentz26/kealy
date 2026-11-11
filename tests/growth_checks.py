"""Require observed guest filesystem growth and persistent allocated data."""
import re

def evaluate_growth(first, second):
    failures = []
    for phase, values in [('first', first), ('second', second)]:
        try:
            disk = int(values['DISK_BYTES'])
            size = int(values['FS_BYTES'])
            extent = int(values['EXTENT_BYTES'])
            if disk != 12 * 1024**3 or not disk * .9 <= size <= disk or extent < 1024**3:
                raise ValueError('Wrong capacity')
        except (KeyError, ValueError, TypeError):
            failures.append(phase + ': capacity/allocation evidence invalid')
        if values.get('WRITE_RC') != '0' or not re.fullmatch('[a-f0-9]{64}', values.get('DATA_SHA', '')):
            failures.append(phase + ': data write/checksum evidence invalid')
    for key in ('DISK_BYTES', 'FS_BYTES', 'EXTENT_BYTES', 'DATA_SHA'):
        if first.get(key) != second.get(key):
            failures.append('Changed across reboot: ' + key)
    return failures
