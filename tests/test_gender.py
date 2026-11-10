from live_translate.gender import neutralize


def test_examples_from_the_test_session():
    assert neutralize("He's very good.", "Çok iyidir.") == "They're very good."
    assert neutralize("He's pretty successful in this car.", "Baya başarılı bu arabada.") == "They're pretty successful in this car."
    assert neutralize("He said?", "dedi?") == "They said?"


def test_agreement_and_pronoun_forms():
    assert neutralize("She likes pizza and he always says so.", "Pizzayı sever ve hep öyle der.") == "They like pizza and they always say so."
    assert neutralize("He has a car, he does it himself.", "Arabası var, kendisi yapıyor.") == "They have a car, they do it themselves."
    assert neutralize("I told him about his talk.", "Ona konuşmasından bahsettim.") == "I told them about their talk."
    assert neutralize("I saw her yesterday with her laptop.", "Onu dün bilgisayarıyla gördüm.") == "I saw them yesterday with their laptop."
    assert neutralize("He wasn't there, he will come.", "Orada değildi, gelecek.") == "They weren't there, they will come."
    assert neutralize("He goes and she watches.", "O gidiyor, o izliyor.") == "They go and they watch."


def test_left_alone_when_turkish_has_gender_or_no_pronoun():
    assert neutralize("My sister said she is tired.", "Ablam yorgun olduğunu söyledi.") == "My sister said she is tired."
    assert neutralize("The man said he is tired.", "Adam yorgun olduğunu söyledi.") == "The man said he is tired."
    assert neutralize("These are the themes of the talk.", "Bunlar konuşmanın temaları.") == "These are the themes of the talk."
    assert neutralize("Shell scripts help.", "Kabuk betikleri yardımcı olur.") == "Shell scripts help."


def test_her_as_object_before_determiners():
    assert neutralize("I gave her the book.", "Ona kitabı verdim.") == "I gave them the book."
    assert neutralize("Her code is great.", "Kodu harika.") == "Their code is great."
