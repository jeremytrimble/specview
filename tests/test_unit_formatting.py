from specview.util import duration_format, freq_format


#def test_freq_format():
#    assert freq_format(1e9) == (1.0, "GHz")
#    assert freq_format(1e6) == (1.0, "MHz")
#    assert freq_format(1e3) == (1.0, "kHz")
#    assert freq_format(1) == (1.0, "Hz")
#    assert freq_format(1e-3) == (1.0, "mHz")
#    assert freq_format(1e-6) == (1.0, "μHz")
#    assert freq_format(1e-9) == (1.0, "nHz")
#    assert freq_format(1e-12) == (1.0, "pHz")
#    assert freq_format(1e-15) == (1.0, "fHz")
#
#    assert freq_format(462.33e6) == (462.33, "MHz")

def test_freq_format():
    assert freq_format(1e9) == "1.000 GHz"
    assert freq_format(1e6) == "1.000 MHz"
    assert freq_format(1e3) == "1.000 kHz"
    assert freq_format(1) == "1.000 Hz"
    assert freq_format(1e-3) == "1.000 mHz"
    assert freq_format(1e-6) == "1.000 μHz"
    assert freq_format(1e-9) == "1.000 nHz"
    assert freq_format(1e-12) == "1.000 pHz"
    assert freq_format(1e-15) == "1.000 fHz"

    assert freq_format(462.33e6) == "462.330 MHz"


def test_duration_format():
    assert duration_format(0) == "0.0s"
    assert duration_format(59.996) == "59.996s"
    assert duration_format(60.0) == "01m00.000s"

    assert duration_format(123e-3) == "123ms"
    assert duration_format(123e-6) == "123μs"
    assert duration_format(123e-9) == "123ns"
    assert duration_format(123e-12) == "123ps"

    assert duration_format(999e-3) == "999ms"
