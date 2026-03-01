from src.crawler import ClauseaCrawler


def test_garbled_binary_content_detected() -> None:
    # Mix of printable and non-printable
    garbled = "a" * 50 + "\x00\x01\x02" * 40 + "b" * 50
    assert ClauseaCrawler._is_garbled_content(garbled) is True


def test_normal_text_not_flagged() -> None:
    normal = (
        "This Privacy Policy describes how we collect and use your personal information. "
        "By using our services you agree to these terms."
    )
    assert ClauseaCrawler._is_garbled_content(normal) is False


def test_high_non_ascii_detected() -> None:
    # High density of non-ASCII characters
    high_unicode = "\u00ff" * 300
    assert ClauseaCrawler._is_garbled_content(high_unicode) is True


def test_empty_and_short_content_not_flagged() -> None:
    assert ClauseaCrawler._is_garbled_content("") is False
    assert ClauseaCrawler._is_garbled_content("short") is False


def test_real_world_garbled_sample() -> None:
    # Sample similar to the one in the user query
    sample = ")S4vvDL\\ڣ:\x18b\x0f9eK\x10C\x0e%j[59DT^\x18\x0e\x07\x059Ѣ\x134j\x15U\x1dԱ=\x0ci\x0ba)AEs7l ^rpV@)\x0bOc:n9\x04\x18\x02nFo#\x01\x14+\x04\x08\x11\x05\x03ϟ\\_zT,\x18NNHSY\x15$w\x16\x02̪u\"N\x122\n\x11\x10'V\x0c\x1f\x0e{\x04l.+\x11kf̴\x1dԆep) 8OR '.9\x1cOf\x13e \x05[\x14\"\x1ac\x11XŅ,O/c\\X^EVZ:(x,-25j'st`1т\x1c1Ci\x01>!ۋ0\x1e+6\x04\x1a.\x02\x12BWʼ\x1fmBԶhf8-1\u0f98\x1cB^K\x07rUЩo\x02Ψ\\O,o\x1ai>\x1b\x11H)\x16b0\x13\n\x7f&V\x0fچxk!\x06py\x1cn\x0cMr78\x189\x07\x1bN\\qGY\x0f \\'d1I3gNP,V\\9i\x0eҟ\x03%\x03iY\\AD7GJ\x7f\x17֛(3jc\\\x03^ \x0b\x17K%Tƒ2{ me\\\x02R>淕vUѬc\u05eb\x0cz,\x08\x17\x08\x01>c\x1dz>ɪ\x12P\\\x1cn\x193\\3$D%oǠK\x0el3t]2ty \\R \x18\x15~/\x06v\x1c\x7fi\x02\x07\\u\\n\x144\x1e\x18-\x02\x02&(9b jhWT)a\x1d\x0e9\\*Wsa\"Á[ff\x10~y\x18'.?\\_R\x1cH8\x0888tbeS\x06\x1an\x1eC\x0f\x05#pX8[O#DX\n!\\~\x07\x01C^ EU\x08BB\x16˪b0/HاY\x12e\x13HvH1̕\\\x15\x10b\"t\x1d\\*}w?Ykg\x07BW/Q̼H]l/$'-[5rA\x7foq/ s\x0e!\x1c\x177\x04KkrE;h]{A7C^@\x19r(\x13ZV\nPꦬT\x1b:]\\_4\x06\n'x۰>ԎJ1O=22\x06@Δ\\]\n"
    assert ClauseaCrawler._is_garbled_content(sample) is True
