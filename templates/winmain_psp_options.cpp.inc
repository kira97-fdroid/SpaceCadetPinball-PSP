
#ifdef SPACECADET_PSP
		Options.Sounds = true;
		Options.Music = false;
		Options.SoundStereo = false;
		Options.FullScreen = false;
		Options.Resolution = 1;
		Options.UniformScaling = true;
		Options.LinearFiltering = false;
		Options.IntegerScaling = false;
		Options.ShowMenu = false;
		Options.HybridSleep = false;
		Options.HideCursor = false;
		Options.UpdatesPerSecond = 120;
		Options.FramesPerSecond = 60;
		Options.UncappedUpdatesPerSecond = false;

		// PSP_PERSIST_AUDIO_OPTIONS_0314
		// Defaults: MUSIC OFF, SFX ON, VIDEO 60 FPS when no config exists.
		PspLoadAudioOptions();

		Options.Key[~GameBindings::LeftFlipper].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_LEFTSHOULDER};
		Options.Key[~GameBindings::RightFlipper].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER};
		Options.Key[~GameBindings::Plunger].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_A};
		Options.Key[~GameBindings::LeftTableBump].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_DPAD_LEFT};
		Options.Key[~GameBindings::RightTableBump].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_DPAD_RIGHT};
		Options.Key[~GameBindings::BottomTableBump].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_DPAD_UP};
		Options.Key[~GameBindings::NewGame].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_BACK};
		Options.Key[~GameBindings::TogglePause].Inputs[2] =
			{InputTypes::GameController, SDL_CONTROLLER_BUTTON_START};
		Options.Key[~GameBindings::Exit].Inputs[2] = {};

		UpdateFrameRate();
#endif
