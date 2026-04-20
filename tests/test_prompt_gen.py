from core.prompt_gen import suggest_whisper_prompt


def test_extracts_author_and_capitalized_nouns():
    episodes = [
        {"title": "KfW-Förderung und Grunderwerbsteuer erklärt",
         "description": "Tobias Schulte spricht mit Marco Lücke über Kapitalanlage und Mietspiegel."},
        {"title": "Grunderwerbsteuer senken — aber wie?",
         "description": "Marco Lücke erklärt die Bruttomietrendite und den Kaufpreisfaktor."},
    ]
    prompt = suggest_whisper_prompt(
        title="Immocation Podcast",
        author="Tobias Schulte",
        episodes=episodes,
    )
    assert "Immocation Podcast" in prompt
    assert "Tobias Schulte" in prompt
    assert "Grunderwerbsteuer" in prompt
    assert "Marco Lücke" in prompt


def test_empty_episodes_still_returns_something():
    p = suggest_whisper_prompt(title="Foo", author="Alice", episodes=[])
    assert "Foo" in p and "Alice" in p


def test_prompt_length_bounded():
    episodes = [{"title": "Bla " * 500, "description": "Bla " * 500}]
    p = suggest_whisper_prompt(title="T", author="A", episodes=episodes)
    assert len(p) <= 450
