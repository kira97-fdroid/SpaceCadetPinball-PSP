import re
from .common import *

def patch_ui_input_runtime(src):
    p = src / "SpaceCadetPinball" / "winmain.cpp"

    # Fresh upstream anchor. 0.3.8 accidentally required Sound.h to
    # exist before this patch ran; 0.3.9 adds it here instead.
    source_before_psp = read(p)
    if source_before_psp.count('#include "font_selection.h"\n') != 1:
        raise RuntimeError(
            "winmain.cpp: unexpected font_selection include layout"
        )

    insert_after_once(
        p,
        '#include "font_selection.h"\n',
        load_template("winmain_psp_support.cpp.inc"),
        "PSP options/audio/FPS/video-profile includes"
    )

    replace_once(
        p,
        '''\t\t800, 556,
\t\tSDL_WINDOW_HIDDEN | SDL_WINDOW_RESIZABLE''',
        '''#ifdef SPACECADET_PSP
\t\t480, 272,
\t\tSDL_WINDOW_HIDDEN
#else
\t\t800, 556,
\t\tSDL_WINDOW_HIDDEN | SDL_WINDOW_RESIZABLE
#endif''',
        "480x272 PSP window"
    )

    replace_once(
        p,
        '''\tauto prefPath = SDL_GetPrefPath("", "SpaceCadetPinball");
\tauto basePath = SDL_GetBasePath();''',
        '''\tauto basePath = SDL_GetBasePath();
#ifdef SPACECADET_PSP
\tauto prefPath = SDL_strdup(basePath ? basePath : "");
#else
\tauto prefPath = SDL_GetPrefPath("", "SpaceCadetPinball");
#endif''',
        "PSP preference path"
    )

    replace_once(
        p,
        '''	SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
	SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");''',
        '''	SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
	SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
#ifdef SPACECADET_PSP
	// PSP_EARLY_LOADING_051: make startup feedback visible before DAT/audio/table initialization.
	SDL_ShowWindow(window);
	PspShowLoadingScreen(renderer);
#endif''',
        "PSP immediate Loading screen"
    )

    replace_once(
        p,
        '''\tbool mixOpened = false, noAudio = strstr(lpCmdLine, "-noaudio") != nullptr;''',
        '''#ifdef SPACECADET_PSP
\tbool mixOpened = false, noAudio = false;
#else
\tbool mixOpened = false, noAudio = strstr(lpCmdLine, "-noaudio") != nullptr;
#endif''',
        "enable PSP audio device"
    )

    regex_replace_once(
        p,
        r'\t\tif \(\(Mix_Init\(MIX_INIT_MID_Proxy\) & MIX_INIT_MID_Proxy\) == 0\)\s*\{\s*printf\("Could not initialize SDL MIDI, music might not work\.\\nSDL Error: %s\\n", SDL_GetError\(\)\);\s*SDL_ClearError\(\);\s*\}',
        '''#ifndef SPACECADET_PSP
		if ((Mix_Init(MIX_INIT_MID_Proxy) & MIX_INIT_MID_Proxy) == 0)
		{
			printf("Could not initialize SDL MIDI, music might not work.\\nSDL Error: %s\\n", SDL_GetError());
			SDL_ClearError();
		}
#endif''',
        "skip unused PSP MIDI proxy init",
        re.MULTILINE
    )

    regex_replace_once(
        p,
        r'\t\{\s*// Load SDL Game Controller definitions from DB\s*unsigned decompressedSize\{\};\s*const auto controllerDb = ImFontAtlas::DecompressCompressedStbData\(\s*EmbeddedData::SDL_GameControllerDB_compressed_data,\s*EmbeddedData::SDL_GameControllerDB_compressed_size,\s*decompressedSize\);\s*auto rw = SDL_RWFromMem\(controllerDb, decompressedSize\);\s*const auto added = SDL_GameControllerAddMappingsFromRW\(rw, 1\);\s*IM_FREE\(controllerDb\);\s*if \(added < 0\)\s*\{\s*printf\("Could not load game controller DB\.\\nSDL Error: %s\\n", SDL_GetError\(\)\);\s*SDL_ClearError\(\);\s*\}\s*\}',
        '''#ifndef SPACECADET_PSP
	{
		// Load SDL Game Controller definitions from DB
		unsigned decompressedSize{};
		const auto controllerDb = ImFontAtlas::DecompressCompressedStbData(
			EmbeddedData::SDL_GameControllerDB_compressed_data,
			EmbeddedData::SDL_GameControllerDB_compressed_size,
			decompressedSize);
		auto rw = SDL_RWFromMem(controllerDb, decompressedSize);
		const auto added = SDL_GameControllerAddMappingsFromRW(rw, 1);
		IM_FREE(controllerDb);
		if (added < 0)
		{
			printf("Could not load game controller DB.\\nSDL Error: %s\\n", SDL_GetError());
			SDL_ClearError();
		}
	}
#endif''',
        "skip unused PSP controller DB decompression",
        re.MULTILINE
    )

    replace_once(
        p,
        "\tstd::set_new_handler(memalloc_failure);\n",
        "\tstd::set_new_handler(memalloc_failure);\n#ifdef SPACECADET_PSP\n\tPspStartupBegin();\n#endif\n",
        "startup profile begin"
    )

    replace_once(
        p,
        "\tPspShowLoadingScreen(renderer);\n#endif",
        "\tPspShowLoadingScreen(renderer);\n\tPspStartupMark(\"renderer + loading\");\n#endif",
        "startup profile renderer"
    )

    replace_once(
        p,
        "\t\tpb::SelectDatFile(searchPaths);",
        "\t\tpb::SelectDatFile(searchPaths);\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"SelectDatFile\");\n#endif",
        "startup profile dat select"
    )

    replace_once(
        p,
        "\t\toptions::InitSecondary();",
        "\t\toptions::InitSecondary();\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"InitSecondary\");\n#endif",
        "startup profile secondary options"
    )

    replace_once(
        p,
        "\t\tSound::Init(mixOpened, Options.SoundChannels, Options.Sounds, Options.SoundVolume);",
        "\t\tSound::Init(mixOpened, Options.SoundChannels, Options.Sounds, Options.SoundVolume);\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"Sound::Init\");\n#endif",
        "startup profile sound init"
    )

    replace_once(
        p,
        "\t\tif (!midi::music_init(mixOpened, Options.MusicVolume))\n\t\t\tOptions.Music = false;",
        "\t\tif (!midi::music_init(mixOpened, Options.MusicVolume))\n\t\t\tOptions.Music = false;\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"music_init\");\n#endif",
        "startup profile music init"
    )

    replace_once(
        p,
        "\t\tif (pb::init())\n\t\t{",
        "#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"before pb::init\");\n#endif\n\t\tif (pb::init())\n\t\t{",
        "startup profile before pb init"
    )

    replace_once(
        p,
        "\t\tfullscrn::init();",
        "#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"pb::init\");\n#endif\n\t\tfullscrn::init();\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"fullscrn::init\");\n#endif",
        "startup profile pb/fullscreen"
    )

    replace_once(
        p,
        "\t\tpb::reset_table();\n\t\tpb::firsttime_setup();",
        "\t\tpb::reset_table();\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"reset_table\");\n#endif\n\t\tpb::firsttime_setup();\n#ifdef SPACECADET_PSP\n\t\tPspStartupMark(\"firsttime_setup\");\n#endif",
        "startup profile table setup"
    )

    replace_once(
        p,
        "\t\telse\n\t\t\tpb::replay_level(false);\n\n\t\tMainLoop();",
        "\t\telse\n\t\t\tpb::replay_level(false);\n#ifdef SPACECADET_PSP\n\t\tPspStartupEnd();\n#endif\n\n\t\tMainLoop();",
        "startup profile end"
    )

    insert_after_once(
        p,
        "\t\toptions::InitPrimary();\n",
        load_template("winmain_psp_options.cpp.inc"),
        "PSP options/controls/performance"
    )

    replace_once(
        p,
        '''\t\tImGui_Render_Init(renderer);
\t\tImGui::StyleColorsDark();

\t\tImGui_ImplSDL2_InitForSDLRenderer(window, Renderer);
\t\tio.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;''',
        '''\t\tImGui::StyleColorsDark();
#ifndef SPACECADET_PSP
\t\tImGui_Render_Init(renderer);
\t\tImGui_ImplSDL2_InitForSDLRenderer(window, Renderer);
\t\tio.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
#endif''',
        "disable ImGui SDL backend on PSP"
    )

    replace_once(
        p,
        '''\t\tif (!Options.FullScreen)
\t\t{
\t\t\tauto resInfo = &fullscrn::resolution_array[fullscrn::GetResolution()];
\t\t\tSDL_SetWindowSize(MainWindow, resInfo->TableWidth, resInfo->TableHeight);
\t\t}
\t\tSDL_ShowWindow(window);
\t\tfullscrn::set_screen_mode(Options.FullScreen);''',
        '''#ifdef SPACECADET_PSP
\t\tOptions.FullScreen = false;
\t\tSDL_SetWindowSize(MainWindow, 480, 272);
\t\tSDL_ShowWindow(window);
\t\tfullscrn::window_size_changed();
#else
\t\tif (!Options.FullScreen)
\t\t{
\t\t\tauto resInfo = &fullscrn::resolution_array[fullscrn::GetResolution()];
\t\t\tSDL_SetWindowSize(MainWindow, resInfo->TableWidth, resInfo->TableHeight);
\t\t}
\t\tSDL_ShowWindow(window);
\t\tfullscrn::set_screen_mode(Options.FullScreen);
#endif''',
        "PSP final window sizing"
    )

    replace_once(
        p,
        '''\t\tImGui_Render_Shutdown();
\t\tImGui_ImplSDL2_Shutdown();
\t\tImGui::DestroyContext();''',
        '''#ifndef SPACECADET_PSP
\t\tImGui_Render_Shutdown();
\t\tImGui_ImplSDL2_Shutdown();
#endif
\t\tImGui::DestroyContext();''',
        "PSP ImGui shutdown"
    )

    # Dedicated PSP realtime main loop.
    # This bypasses the desktop frame-duration clamp that caused slow motion.
    s = read(p)
    realtime_marker = "PSP_REALTIME_LOOP_051"
    if realtime_marker not in s:
        main_loop_pos = s.find("void winmain::MainLoop()")
        if main_loop_pos < 0:
            raise RuntimeError("winmain.cpp: MainLoop not found")
        open_pos = s.find("{", main_loop_pos)
        if open_pos < 0:
            raise RuntimeError("winmain.cpp: MainLoop opening brace not found")

        psp_loop = load_template("winmain_psp_loop.cpp.inc")
        s = s[:open_pos + 1] + psp_loop + s[open_pos + 1:]
        write(p, s)
        print("[ok]   PSP realtime loop 120 Hz physics / runtime 30-60 FPS")
    else:
        print("[skip] PSP realtime loop")

    # Structural ImGui event bypass on PSP.
    # Cross/A SDL events are swallowed because the dedicated PSP loop
    # handles the physical Cross button directly.
    s = read(p)
    event_marker = "PSP_EVENT_BYPASS_030"
    if event_marker not in s:
        handler_pos = s.find("int winmain::event_handler(const SDL_Event* event)")
        if handler_pos < 0:
            raise RuntimeError("winmain.cpp: event_handler not found")
        block_start = s.find("\tauto inputDown = false;", handler_pos)
        if block_start < 0:
            raise RuntimeError("winmain.cpp: ImGui capture block start not found")
        final_switch = s.find("\tswitch (event->type)\n\t{\n\tcase SDL_QUIT:", block_start)
        if final_switch < 0:
            raise RuntimeError("winmain.cpp: gameplay event switch not found")

        original_capture = s[block_start:final_switch]
        wrapped = (
            "#ifndef SPACECADET_PSP\n"
            "\t// PSP_EVENT_BYPASS_030\n"
            + original_capture
            + "#else\n"
            "\t// Native PSP input owns Cross and the Options overlay.\n"
            "\tif (event->type == SDL_CONTROLLERBUTTONDOWN ||\n"
            "\t    event->type == SDL_CONTROLLERBUTTONUP)\n"
            "\t{\n"
            "\t\tif (PspOptionsOpen ||\n"
            "\t\t    event->cbutton.button == SDL_CONTROLLER_BUTTON_A)\n"
            "\t\t\treturn 1;\n"
            "\t}\n"
            "#endif\n"
        )
        s = s[:block_start] + wrapped + s[final_switch:]
        write(p, s)
        print("[ok]   PSP event path / direct Cross")
    else:
        print("[skip] PSP event path / direct Cross")


def patch_pause_prompt(src):
    root = src / "SpaceCadetPinball"
    replacements = (
        ("F3 to Resume", "to Resume"),
        ("F3 to resume", "to Resume"),
        ("F3 TO RESUME", "to Resume"),
        ("F2 starts new game", "SELECT Starts New Game"),
        ("F2 Starts New Game", "SELECT Starts New Game"),
        ("F2 STARTS NEW GAME", "SELECT Starts New Game"),
        ("Game Paused", "Paused START"),
        ("GAME PAUSED", "Paused START"),
        ("Game paused", "Paused START"),
    )

    text_suffixes = {
        ".cpp", ".h", ".hpp", ".c", ".cc",
        ".txt", ".ini", ".json", ".rc", ".md"
    }

    matches = 0
    changed_files = []

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        original = content
        for old, new in replacements:
            count = content.count(old)
            if count:
                matches += count
                content = content.replace(old, new)

        if content != original:
            path.write_text(content, encoding="utf-8")
            changed_files.append(str(path.relative_to(src)))

    if matches <= 0:
        raise RuntimeError(
            "Pause prompt not found in upstream source; "
            "refusing to build an EBOOT without the PSP pause prompt"
        )

    print(f"[ok]   PSP UI prompts ({matches} replacement(s))")
    for name in changed_files:
        print(f"       {name}")


def strip_startup_profiler(src):
    """Remove temporary 0.5.1-0.5.5 startup profiling from the stable PSP build.

    patch_winmain still applies the historical instrumentation first so that the
    long-lived patch sequence stays compatible with the validated upstream
    anchors; this pass removes every runtime profiler symbol/call before compile.
    The immediate LOADING screen itself is intentionally preserved.
    """
    p = src / "SpaceCadetPinball" / "winmain.cpp"
    s = read(p)

    begin = s.find("\tUint64 PspStartupBeginCounter = 0;")
    end = s.find("\n\tvoid PspShowLoadingScreen", begin)
    if begin < 0 or end < 0:
        raise RuntimeError("winmain.cpp: stable startup-profiler block not found")
    s = s[:begin] + s[end + 1:]

    # Remove the temporary measurement calls. The renderer/loading call sits
    # inside the real PSP loading #ifdef; the others are standalone #ifdefs.
    s = re.sub(r'^[ \t]*PspStartup(?:Begin|Mark|End)\([^\n;]*\);\n', '', s, flags=re.MULTILINE)
    # Drop preprocessor blocks that became empty after removing profiler calls.
    previous = None
    while previous != s:
        previous = s
        s = re.sub(r'#ifdef SPACECADET_PSP\n[ \t]*#endif\n?', '', s)

    leftovers = [token for token in ("PspStartupBegin", "PspStartupMark", "PspStartupEnd", "startup_profile.txt") if token in s]
    if leftovers:
        raise RuntimeError("winmain.cpp: startup profiler cleanup incomplete: " + ", ".join(leftovers))

    write(p, s)
    print("[ok]   remove diagnostic startup profiler (stable)")

