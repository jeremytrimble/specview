from specview.util import duration_format, freq_format, parse_unit_prefix, parse_time_str, parse_freq_str
import pytest


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

    assert duration_format(123e-3) ==  "123.0ms"
    assert duration_format(123e-6) ==  "123.0μs"
    assert duration_format(123e-9) ==  "123.0ns"
    assert duration_format(123e-12) == "123.0ps"

    assert duration_format(-123e-12) == "-123.0ps"

    assert duration_format(999e-3) == "999.0ms"

    assert duration_format( 59*60 + 59.999) == "59m59.999s"
    assert duration_format( -(59*60 + 59.999)) == "-59m59.999s"

    assert duration_format( 1*3600 + 2*60 + 3.456) == "1h02m03.456s"


def test_parse_unit_prefix():
    # Basic number parsing
    assert parse_unit_prefix("1.5") == (1.5, "")
    assert parse_unit_prefix("-1.5") == (-1.5, "")
    assert parse_unit_prefix("1e6") == (1e6, "")
    assert parse_unit_prefix("-1.5e-6") == (-1.5e-6, "")
    
    # SI prefixes without units
    assert parse_unit_prefix("1.5k") == (1500.0, "")
    assert parse_unit_prefix("-1.5k") == (-1500.0, "")
    assert parse_unit_prefix("1.5M") == (1.5e6, "")
    assert parse_unit_prefix("1.5G") == (1.5e9, "")
    assert parse_unit_prefix("1.5T") == (1.5e12, "")
    assert parse_unit_prefix("1.5m") == (1.5e-3, "")
    assert parse_unit_prefix("1.5µ") == (1.5e-6, "")
    assert parse_unit_prefix("1.5μ") == (1.5e-6, "")  # alternative form
    assert parse_unit_prefix("1.5u") == (1.5e-6, "")  # ASCII form
    assert parse_unit_prefix("1.5n") == (pytest.approx(1.5e-9), "")
    assert parse_unit_prefix("1.5p") == (pytest.approx(1.5e-12), "")
    assert parse_unit_prefix("1.5f") == (pytest.approx(1.5e-15), "")
    
    # SI prefixes with units
    assert parse_unit_prefix("1.5kHz") == (1500.0, "Hz")
    assert parse_unit_prefix("1.5MHz") == (1.5e6, "Hz")
    assert parse_unit_prefix("1.5ms") == (1.5e-3, "s")
    
    # Edge cases
    assert parse_unit_prefix("0") == (0.0, "")
    assert parse_unit_prefix("-0") == (0.0, "")
    assert parse_unit_prefix("1.5 MHz") == (1.5e6, "Hz")  # space handling
    
    # Error cases
    with pytest.raises(ValueError):
        parse_unit_prefix("")
    with pytest.raises(ValueError):
        parse_unit_prefix("abc")
    assert parse_unit_prefix("1.5x") == (1.5, "x")  # invalid prefix


def test_parse_time_str():
    # Basic time values
    assert parse_time_str("1.5") == 1.5
    assert parse_time_str("1.5s") == 1.5
    assert parse_time_str("-1.5s") == -1.5
    
    # SI prefixes
    assert parse_time_str("1.5ms") == 1.5e-3
    assert parse_time_str("1.5µs") == 1.5e-6
    assert parse_time_str("1.5μs") == 1.5e-6  # alternative form
    assert parse_time_str("1.5us") == 1.5e-6  # ASCII form
    assert parse_time_str("1.5ns") == pytest.approx(1.5e-9)
    assert parse_time_str("1.5ps") == pytest.approx(1.5e-12)
    assert parse_time_str("1.5fs") == pytest.approx(1.5e-15)
    
    # Scientific notation
    assert parse_time_str("1.5e-3s") == 1.5e-3
    assert parse_time_str("-1.5e-3s") == -1.5e-3
    
    # Error cases
    with pytest.raises(ValueError):
        parse_time_str("1.5min")  # invalid unit
    with pytest.raises(ValueError):
        parse_time_str("")  # empty string
    with pytest.raises(ValueError):
        parse_time_str("abc")  # invalid format


def test_parse_freq_str():
    # Basic frequency values
    assert parse_freq_str("1.5") == 1.5
    assert parse_freq_str("1.5Hz") == 1.5
    assert parse_freq_str("-1.5Hz") == -1.5
    
    # SI prefixes
    assert parse_freq_str("1.5kHz") == 1.5e3
    assert parse_freq_str("1.5MHz") == 1.5e6
    assert parse_freq_str("1.5GHz") == 1.5e9
    assert parse_freq_str("1.5THz") == 1.5e12
    assert parse_freq_str("1.5mHz") == 1.5e-3
    assert parse_freq_str("1.5µHz") == 1.5e-6
    assert parse_freq_str("1.5μHz") == 1.5e-6  # alternative form
    assert parse_freq_str("1.5uHz") == 1.5e-6  # ASCII form
    assert parse_freq_str("1.5nHz") == pytest.approx(1.5e-9)
    assert parse_freq_str("1.5pHz") == pytest.approx(1.5e-12)
    assert parse_freq_str("1.5fHz") == pytest.approx(1.5e-15)
    
    # Scientific notation
    assert parse_freq_str("1.5e6Hz") == 1.5e6
    assert parse_freq_str("-1.5e6Hz") == -1.5e6
    
    # Error cases
    with pytest.raises(ValueError):
        parse_freq_str("1.5khz")  # wrong case
    with pytest.raises(ValueError):
        parse_freq_str("")  # empty string
    with pytest.raises(ValueError):
        parse_freq_str("abc")  # invalid format