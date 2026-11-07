# Install SkillBlend with Claude Code

Paste this into Claude Code. Claude installs SkillBlend, learns how you model from your own Blender files, and installs a skill so it models the same way. You only answer a few questions along the way (where your models are, what to call your skill).

```text
Install SkillBlend (https://github.com/1337VIPER/skillblend) and use it to learn how I model in Blender, then make me a skill from it.

1. Ask me where to put it (default: a "skillblend" folder in my home folder) and clone the repo there.
2. Check that Python 3.9 or newer is available, and find my Blender install (4.2 or newer). If you can't find Blender, ask me for the path. Then run:
   python skillblend.py config --blender "<path to blender>"
3. Install the SkillBlend helper skill:
   python skillblend.py install-driver
4. Ask me which folder holds my Blender models, and whether I keep a kitbash or insert library in another folder. Then run:
   python skillblend.py learn "<models folder>" ["<kit folder>"]
5. Run "python skillblend.py report" and explain to me, in plain language, what it learned about how I model. Point out anything that looks off, and ask whether I want to leave any file out.
6. Ask me three things: what to call my skill, whether my kitbash pieces are my own work (if yes, run: python skillblend.py answer kit-library kit_redistribute true), and whether to copy my .blend files into the skill so you can study them (if yes, add --examples). Then build and install it:
   python skillblend.py build --name "<name>" [--examples]
   python skillblend.py install "<the folder the build printed>"
7. Tell me to start a new Claude Code session, and give me two example prompts to try my new skill.

Never open, change or save any of my .blend files: SkillBlend only reads them. If I'd rather click through it myself, run "python skillblend.py app" instead of steps 4 to 6 and tell me to follow the three steps in my browser.
```

The prompt doesn't need anything installed first apart from Claude Code, Python, Git and Blender.
