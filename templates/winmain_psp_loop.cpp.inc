
#ifdef SPACECADET_PSP
	// PSP_REALTIME_LOOP_051
	//
	// Dedicated PSP loop:
	// - physics uses a real-time fixed step of 8.3333333 ms (120 Hz);
	// - rendering target is selected at runtime: 30 or 60 FPS;
	// - Cross is read directly from PSP hardware and does not rely on
	//   SDL controller release events.
	bQuit = false;

	const double perfFrequency =
		static_cast<double>(SDL_GetPerformanceFrequency());
	constexpr double physicsStepMs = 1000.0 / 120.0;
	
	Uint64 previousCounter = SDL_GetPerformanceCounter();
	double physicsAccumulatorMs = 0.0;
	double renderAccumulatorMs = 0.0;
	Uint64 fpsWindowStart = previousCounter;
	int fpsFrameCount = 0;
	int pspDisplayedFps = 0;
	double benchmarkPhysicsAccumMs = 0.0;
	Uint64 benchmarkLastPresentCounter = previousCounter;
	Uint64 benchmarkLastHardwareSample = previousCounter;
	bool previousCrossDown = false;
	bool previousTriangleDown = false;
	bool previousUpDown = false;
	bool previousDownDown = false;
	bool previousLeftDown = false;
	bool previousRightDown = false;

	sceCtrlSetSamplingCycle(0);
	sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);

	while (true)
	{
		if (!ProcessWindowMessages() || bQuit)
			break;

		const Uint64 currentCounter = SDL_GetPerformanceCounter();
		double elapsedMs =
			static_cast<double>(currentCounter - previousCounter)
			* 1000.0 / perfFrequency;
		previousCounter = currentCounter;

		// Do not allow a suspend/debug pause to create a huge catch-up burst.
		if (elapsedMs < 0.0)
			elapsedMs = 0.0;
		if (elapsedMs > 100.0)
			elapsedMs = 100.0;

		if (no_time_loss)
		{
			no_time_loss = false;
			elapsedMs = 0.0;
			physicsAccumulatorMs = 0.0;
			renderAccumulatorMs = 0.0;
			fpsWindowStart = currentCounter;
			fpsFrameCount = 0;
			pspDisplayedFps = 0;
		}

		// Native PSP controls: Cross plus Options overlay.
		SceCtrlData pspPad{};
		if (sceCtrlPeekBufferPositive(&pspPad, 1) > 0)
		{
			const bool crossDown = (pspPad.Buttons & PSP_CTRL_CROSS) != 0;
			const bool triangleDown = (pspPad.Buttons & PSP_CTRL_TRIANGLE) != 0;
			const bool upDown = (pspPad.Buttons & PSP_CTRL_UP) != 0;
			const bool downDown = (pspPad.Buttons & PSP_CTRL_DOWN) != 0;
			const bool leftDown = (pspPad.Buttons & PSP_CTRL_LEFT) != 0;
			const bool rightDown = (pspPad.Buttons & PSP_CTRL_RIGHT) != 0;

			if (triangleDown && !previousTriangleDown)
			{
				if (!PspOptionsOpen && previousCrossDown)
				{
					const GameInput crossInput{
						InputTypes::GameController,
						SDL_CONTROLLER_BUTTON_A
					};
					pb::InputUp(crossInput);
				}
				PspOptionsOpen = !PspOptionsOpen;
				physicsAccumulatorMs = 0.0;
			}

			if (PspOptionsOpen)
			{
				if (upDown && !previousUpDown)
					PspOptionsSelection = (PspOptionsSelection + 5) % 6;
				if (downDown && !previousDownDown)
					PspOptionsSelection = (PspOptionsSelection + 1) % 6;

				const bool crossPressed = crossDown && !previousCrossDown;
				const bool leftPressed = leftDown && !previousLeftDown;
				const bool rightPressed = rightDown && !previousRightDown;
				const bool toggle = crossPressed || leftPressed || rightPressed;

				if (toggle)
				{
					if (PspOptionsSelection == 0)
						PspSetMusicEnabled(!options::Options.Music);
					else if (PspOptionsSelection == 1)
						PspSetSfxEnabled(!options::Options.Sounds);
					else if (PspOptionsSelection == 2)
						PspSetFpsEnabled(!PspShowFps);
					else if (PspOptionsSelection == 3)
					{
						const int delta = leftPressed ? -1 : 1;
						PspSetVideoProfile(options::Options.Resolution + delta);
						renderAccumulatorMs = 0.0;
					}
					else if (PspOptionsSelection == 4)
					{
						const int delta = leftPressed ? -1 : 1;
						PspSetCpuClockProfile(delta);
					}
					else
						PspSetBenchmarkEnabled(!PspShowBenchmark);
				}
			}
			else if (crossDown != previousCrossDown)
			{
				const GameInput crossInput{
					InputTypes::GameController,
					SDL_CONTROLLER_BUTTON_A
				};
				if (crossDown)
					pb::InputDown(crossInput);
				else
					pb::InputUp(crossInput);
			}

			previousCrossDown = crossDown;
			previousTriangleDown = triangleDown;
			previousUpDown = upDown;
			previousDownDown = downDown;
			previousLeftDown = leftDown;
			previousRightDown = rightDown;
		}

		const Uint64 benchmarkPhysicsStart = SDL_GetPerformanceCounter();
		if (!single_step && !PspOptionsOpen)
		{
			physicsAccumulatorMs += elapsedMs;

			// 100 ms elapsed cap means at most twelve catch-up steps.
			while (physicsAccumulatorMs + 0.0001 >= physicsStepMs)
			{
				pb::frame(static_cast<float>(physicsStepMs));
				physicsAccumulatorMs -= physicsStepMs;
			}
		}
		else
		{
			// Do not catch up the simulation after unpausing.
			physicsAccumulatorMs = 0.0;
		}
		const Uint64 benchmarkPhysicsEnd = SDL_GetPerformanceCounter();
		benchmarkPhysicsAccumMs += static_cast<double>(benchmarkPhysicsEnd - benchmarkPhysicsStart) * 1000.0 / perfFrequency;

		const double renderStepMs = 1000.0 /
			(options::Options.FramesPerSecond >= 60 ? 60.0 : 30.0);
		renderAccumulatorMs += elapsedMs;
		if (renderAccumulatorMs >= renderStepMs)
		{
			const Uint64 benchmarkRenderStart = SDL_GetPerformanceCounter();
			gdrv::grtext_draw_ttext_in_box();

			// PSP_PILLARBOX_BLACK_0312
			// Always clear the full PSP framebuffer to black before drawing
			// the aspect-correct table. This keeps the side bars black even
			// if any overlay changed SDL's draw colour.
			SDL_SetRenderDrawColor(Renderer, 0, 0, 0, 255);
			SDL_RenderClear(Renderer);
			render::PresentVScreen();

			if (PspOptionsOpen)
				PspDrawOptionsMenu(
					Renderer,
					static_cast<bool>(options::Options.Music),
					static_cast<bool>(options::Options.Sounds),
					PspShowFps,
					PspShowBenchmark,
					(options::Options.FramesPerSecond >= 60 ? 1 : 0),
					PspCpuClockMHz,
					PspOptionsSelection);

			PspDrawFpsCounter(Renderer, pspDisplayedFps);
			if (!PspOptionsOpen)
				PspDrawBenchmarkOverlay(Renderer);
			const Uint64 benchmarkRenderEnd = SDL_GetPerformanceCounter();
			const Uint64 benchmarkPresentStart = benchmarkRenderEnd;
			SDL_RenderPresent(Renderer);
			const Uint64 benchmarkPresentEnd = SDL_GetPerformanceCounter();

			const double benchmarkRenderMs = static_cast<double>(benchmarkRenderEnd - benchmarkRenderStart) * 1000.0 / perfFrequency;
			const double benchmarkPresentMs = static_cast<double>(benchmarkPresentEnd - benchmarkPresentStart) * 1000.0 / perfFrequency;
			const double benchmarkFrameMs = benchmarkLastPresentCounter == 0 ? 0.0 : static_cast<double>(benchmarkPresentEnd - benchmarkLastPresentCounter) * 1000.0 / perfFrequency;
			benchmarkLastPresentCounter = benchmarkPresentEnd;
			PspBenchmark.frameMs = benchmarkFrameMs;
			PspBenchmark.physicsMs = benchmarkPhysicsAccumMs;
			PspBenchmark.renderMs = benchmarkRenderMs;
			PspBenchmark.presentMs = benchmarkPresentMs;
			PspBenchmark.cpuLoadPct = std::max(0.0, std::min(100.0, (benchmarkPhysicsAccumMs + benchmarkRenderMs) * 100.0 / renderStepMs));
			PspBenchmark.gpuLoadPct = std::max(0.0, std::min(100.0, benchmarkPresentMs * 100.0 / renderStepMs));
			benchmarkPhysicsAccumMs = 0.0;
			if (static_cast<double>(benchmarkPresentEnd - benchmarkLastHardwareSample) / perfFrequency >= 0.5)
			{
				PspUpdateHardwareBenchmark();
				benchmarkLastHardwareSample = benchmarkPresentEnd;
			}

			++fpsFrameCount;
			const Uint64 fpsNow = benchmarkPresentEnd;
			const double fpsWindowSeconds =
				static_cast<double>(fpsNow - fpsWindowStart) / perfFrequency;
			if (fpsWindowSeconds >= 1.0)
			{
				pspDisplayedFps = static_cast<int>(std::round(
					static_cast<double>(fpsFrameCount) / fpsWindowSeconds));
				PspBenchmark.fps = pspDisplayedFps;
				fpsFrameCount = 0;
				fpsWindowStart = fpsNow;
			}

			// Preserve the normal sub-frame remainder. With the 1 ms PSP yield,
			// resetting to zero quantizes 60 FPS to roughly 17 ms/frame (~58.8 FPS).
			renderAccumulatorMs -= renderStepMs;
			// If we missed more than one whole video interval, drop the backlog
			// instead of rendering a burst of catch-up frames.
			if (renderAccumulatorMs >= renderStepMs)
				renderAccumulatorMs = 0.0;
		}

		// Yield briefly; game timing is based on the performance counter,
		// not on this delay.
		sceKernelDelayThread(1000);
	}

	return;
#endif
