import re, itertools, sys, time, math

# let's do this just once, not at every call
_clean_control_chars = "".join(
    map(chr, itertools.chain(range(0x00, 0x20), range(0x7F, 0xA0)))
)
_clean_control_char_re = re.compile("[%s]" % re.escape(_clean_control_chars))


def cleanup_str(s):
    return _clean_control_char_re.sub("", s)


def print_err(*args, **kwargs):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp, ) + args), file=sys.stderr, **kwargs)


# this is based on https://www.regular-expressions.info/email.html
def is_email(text: str):
    return re.match(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
