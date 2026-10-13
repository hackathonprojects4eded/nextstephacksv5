"""Run: uv run python -m jams.test_room_code"""

from jams.room_code import code_for, host_for, lan_ip


def test_codes():
    for ip in ["192.168.68.56", "10.0.0.1", "0.0.0.0", "255.255.255.255", lan_ip()]:
        code = code_for(ip)
        assert len(code) == 7 and code.isalnum() and code == code.upper(), code
        assert host_for(code) == ip and host_for(f" {code.lower()} ") == ip  # typed loosely
    for typo in ["", "ABC!23", "ZZZZZZZZ", "-1"]:
        try:
            host_for(typo)
            raise AssertionError(f"{typo!r} should be rejected")
        except ValueError:
            pass


if __name__ == "__main__":
    test_codes()
    print("ok")
