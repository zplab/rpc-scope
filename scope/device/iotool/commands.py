# This code is licensed under the MIT License (see LICENSE file for details)

def _make_command(*elements):
    return ' '.join(map(str, elements))

def wait_high(pin):
    return _make_command('wh', pin)

def wait_low(pin):
    return _make_command('wl', pin)

def wait_change(pin):
    return _make_command('wc', pin)

def wait_time(time):
    return _make_command('wt', time)

def read_digital(pin):
    return _make_command('rd', pin)

def read_analog(pin):
    return _make_command('ra', pin)

def delay_ms(delay):
    return _make_command('dm', delay)

def delay_us(delay):
    return _make_command('du', delay)

def timer_begin():
    return _make_command('tb')

def timer_end():
    return _make_command('te')

def pwm(pin, value):
    return _make_command('pm', pin, value)

def set_high(pin):
    return _make_command('sh', pin)

def set_low(pin):
    return _make_command('sl', pin)

def set_tristate(pin):
    return _make_command('st', pin)

def char_transmit(byte):
    return _make_command('ct', byte)

def char_receive():
    return _make_command('cr')

def loop(index, count):
    return _make_command('lo', index, count)

def goto(index):
    return _make_command('go', index)
