"""Curated, cited neuroscience education cards (Prompt A, F4).

Short, factual, cautious, and non-prescriptive: these cards explain how some parts
of the brain and body are understood to work. They never advise the reader to do
anything, and they never claim more than the cited literature supports. Any card
whose science is contested says so in the card itself.

Content is an immutable tuple of frozen dataclasses; the UI only reads it. One card
is shown per day, chosen from the calendar date alone by :func:`fact_for_date`.
"""

from __future__ import annotations

from datetime import date

from .models import BrainFact

BRAIN_FACTS: tuple[BrainFact, ...] = (
    BrainFact(
        title="The amygdala and the stress response",
        body=(
            "The amygdala is a small, almond-shaped cluster in each temporal lobe. It "
            "flags what matters for survival and starts fast alarm — quicker heart, "
            "sharper attention — before slower reasoning catches up: useful for real "
            "danger, tiring when nothing is wrong."
        ),
        source="Phelps & LeDoux, Neuron 2005; LeDoux, Curr Biol 2012",
    ),
    BrainFact(
        title="The prefrontal cortex and emotion regulation",
        body=(
            "The prefrontal cortex, behind the forehead, supports planning and holding "
            "ideas in mind, and sends signals that dampen the amygdala's alarm. That "
            "top-down pathway works better when someone is rested and feels safe, less "
            "well under acute stress or sleep loss."
        ),
        source="Arnsten, Nat Rev Neurosci 2009; Etkin, Egner & Kalisch, Trends Cogn Sci 2011",
    ),
    BrainFact(
        title="The hippocampus and prolonged stress",
        body=(
            "The hippocampus helps form new memories and track where you are, and is "
            "among the regions most sensitive to stress hormones. Chronic-stress studies "
            "report smaller hippocampal volume and weaker memory, though most human "
            "evidence is correlational."
        ),
        source="McEwen, NEJM 1998; Lupien et al., Nat Rev Neurosci 2009",
    ),
    BrainFact(
        title="Sleep and the brain's waste clearance",
        body=(
            "During sleep the space between brain cells widens and fluid flow increases, "
            "speeding removal of metabolic waste including amyloid-beta — the glymphatic "
            "system. Most direct evidence comes from animals; in humans the picture is "
            "still being mapped."
        ),
        source="Xie et al., Science 2013; Jessen et al., Neurochem Res 2015",
    ),
    BrainFact(
        title="Exercise, neuroplasticity, and mood",
        body=(
            "Physical activity raises blood flow to the brain and growth factors such as "
            "BDNF that support connections between neurons. Trials link regular aerobic "
            "exercise to modest mood and memory gains. Effects vary widely, and it is not "
            "a treatment."
        ),
        source="Cotman & Berchtold, Trends Neurosci 2002; Erickson et al., PNAS 2011",
    ),
    BrainFact(
        title="Serotonin, dopamine, and the 'chemical imbalance' story",
        body=(
            "Popular accounts call depression low serotonin and reward a dopamine 'hit'. "
            "A 2022 umbrella review found no consistent support for a simple serotonin "
            "deficit, and dopamine looks more like a motivation and learning signal than "
            "pleasure. That does not make treatment ineffective."
        ),
        source="Moncrieff et al., Mol Psychiatry 2023; Salamone & Correa, Neuron 2012",
    ),
    BrainFact(
        title="The HPA axis",
        body=(
            "The hypothalamic-pituitary-adrenal axis is the body's main slow stress "
            "pathway: the hypothalamus signals the pituitary, which tells the adrenal "
            "glands to release cortisol. Chronic stress can distort cortisol's feedback "
            "loop, flattening the daily rhythm."
        ),
        source="Tsigos & Chrousos, J Psychosom Res 2002; Herman et al., Compr Physiol 2016",
    ),
    BrainFact(
        title="Why naming an emotion can help",
        body=(
            "Naming an emotion is called affect labelling. In imaging studies it is "
            "linked to less amygdala activity and more activity in prefrontal regions, "
            "and people report the feeling as less intense afterwards. It is modest and "
            "short-lived, not a cure."
        ),
        source="Lieberman et al., Psychol Sci 2007; Torre & Lieberman, Emotion 2015",
    ),
    BrainFact(
        title="Sleep and memory",
        body=(
            "Sleep is not a pause in learning. In slow-wave sleep the hippocampus replays "
            "the day's patterns into cortical networks for longer storage; REM has been "
            "linked to integrating new information. Short sleep costs consolidation and "
            "next-day attention."
        ),
        source="Walker & Stickgold, Neuron 2006; Rasch & Born, Physiol Rev 2013",
    ),
    BrainFact(
        title="A contested question: new neurons in adult humans",
        body=(
            "Whether adult humans grow new neurons in the hippocampus has been debated "
            "for decades: some studies report ongoing neurogenesis, a widely cited 2018 "
            "study found little. The disagreement is about methods and detection limits — "
            "the brain clearly rewires existing connections."
        ),
        source="Boldrini et al., Cell Stem Cell 2018; Sorrells et al., Nature 2018",
    ),
)


def facts_in_display_order() -> tuple[BrainFact, ...]:
    """Return every brain-fact card in its curated display order."""
    return BRAIN_FACTS


def fact_for_date(day: date) -> BrainFact:
    """Return the card shown on ``day``.

    The rotation is deterministic: each day steps to the next card in the curated
    order and the sequence repeats every ``fact_count()`` days, so the same date
    always shows the same card and every card comes up in turn.
    """
    return BRAIN_FACTS[day.toordinal() % len(BRAIN_FACTS)]


def fact_count() -> int:
    """Return how many education cards are available."""
    return len(BRAIN_FACTS)


def fact_by_title(title: str) -> BrainFact:
    """Return the card with ``title``. Raises ``KeyError`` when absent."""
    for fact in BRAIN_FACTS:
        if fact.title == title:
            return fact
    raise KeyError(f"Unknown brain fact {title!r}")
