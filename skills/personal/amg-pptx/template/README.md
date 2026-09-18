# `template/` — bring your own

The branded `.pptx` this skill was built against is **not included** in the
public copy: it carried an organisation's logos and slide-master branding.

Drop your own 16:9 template here as `institute.pptx`. It needs exactly the two
layouts `scripts/build_deck.py` uses (a title layout and a content layout), and
the geometry notes in `style/STYLE.md` assume a bottom footer band holding a
logo on the left and the slide number on the right. Adjust the constants near
the top of `scripts/build_deck.py` if your template's bands differ.
