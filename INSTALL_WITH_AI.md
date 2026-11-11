# Install SkillBlend with your AI assistant

Paste this into any coding assistant that can run commands: Claude Code, OpenAI Codex, Cursor's agent, Gemini CLI, GitHub Copilot's agent, Windsurf and others. It installs SkillBlend, learns how you model from your own Blender files, and installs a skill so the assistant models the same way. You only answer a few questions along the way.

```text
Install SkillBlend (https://github.com/1337VIPER/skillblend) and use it to learn how I model in Blender, then make me a skill for you from it.

1. Ask me where to put it (default: a "skillblend" folder in my home folder) and clone the repo there.
2. Check that Python 3.9 or newer is available, and find my Blender install (4.2 or newer). If you can't find Blender, ask me for the path. Then run:
   python skillblend.py config --blender "<path to blender>"
3. If you are Claude Code, install the SkillBlend helper skill: python skillblend.py install-driver
   (Other assistants: read AGENTS.md in the repo instead; it explains the same steps.)
4. Ask me which folder holds my Blender models, and whether I keep a kitbash or insert library in another folder. Then run:
   python skillblend.py learn "<models folder>" ["<kit folder>"]
5. Run "python skillblend.py report" and explain to me, in plain language, what it learned about how I model. Point out anything that looks off, and ask whether I want to leave any file out.
6. Ask me three things: what to call my skill, whether my kitbash pieces are my own work (if yes, run: python skillblend.py answer kit-library kit_redistribute true), and whether to copy my .blend files into the skill so you can study them (if yes, add --examples). Then build it:
   python skillblend.py build --name "<name>" [--examples]
7. Install it for the assistant I'm using, with --for set to yourself: claude (Claude Code), codex (OpenAI Codex and other AGENTS.md tools), cursor, gemini (Gemini CLI), copilot or windsurf. For anything but Claude Code, ask me for the project folder I work in:
   python skillblend.py install "<the folder the build printed>" --for <you> [--project-dir "<project>"]
   If I use a plain chat model (ChatGPT, a local model in Ollama or LM Studio), give me exports/system-prompt.md from the built folder to paste in as the system prompt.
8. Tell me to start a new session, and give me two example prompts to try my new skill.

Never open, change or save any of my .blend files: SkillBlend only reads them. If I'd rather click through it myself, run "python skillblend.py app" instead of steps 4 to 7 and tell me to follow the three steps in my browser.
```

You need Python, Git and Blender installed. For a plain chat model with no command access, run the app yourself (`python skillblend.py app`) and use **Copy a system prompt** in step 3.
