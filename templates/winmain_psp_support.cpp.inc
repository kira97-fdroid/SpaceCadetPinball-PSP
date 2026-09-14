#include "Sound.h"
#ifdef SPACECADET_PSP
#include <pspctrl.h>
#include <pspthreadman.h>
#include <psppower.h>
#include <pspsysmem.h>

namespace
{
	bool PspOptionsOpen = false;
	int PspOptionsSelection = 0;
	bool PspShowFps = false;
	bool PspShowBenchmark = false;
	int PspCpuClockMHz = 266;

	struct PspBenchmarkSnapshot
	{
		int fps = 0;
		double frameMs = 0.0;
		double physicsMs = 0.0;
		double renderMs = 0.0;
		double presentMs = 0.0;
		double cpuLoadPct = 0.0;
		double gpuLoadPct = 0.0;
		int cpuMHz = 0;
		int busMHz = 0;
		unsigned freeMemKb = 0;
		int batteryPct = -1;
		int batteryTempC = -1;
	};

	PspBenchmarkSnapshot PspBenchmark{};

	enum class PspClockApplyStatus
	{
		Ok,
		Locked,
		ApplyFailed
	};

	PspClockApplyStatus PspClockStatus = PspClockApplyStatus::Ok;
	int PspClockApplyResult = 0;

	const char* PspClockStatusName()
	{
		switch (PspClockStatus)
		{
		case PspClockApplyStatus::Locked: return "LOCKED";
		case PspClockApplyStatus::ApplyFailed: return "FAILED";
		default: return "OK";
		}
	}

	void PspApplyCpuClock()
	{
		const int requestedCpu = PspCpuClockMHz;
		const int requestedBus = requestedCpu / 2;
		PspClockApplyResult = scePowerSetClockFrequency(requestedCpu, requestedCpu, requestedBus);
		if (PspClockApplyResult < 0)
		{
			// Some firmwares may reject the combined setter but still allow the dedicated setters.
			const int cpuResult = scePowerSetCpuClockFrequency(requestedCpu);
			const int busResult = scePowerSetBusClockFrequency(requestedBus);
			PspClockApplyResult = (cpuResult >= 0 && busResult >= 0) ? 0 : -1;
		}

		const int actualCpu = scePowerGetCpuClockFrequencyInt();
		const int actualBus = scePowerGetBusClockFrequencyInt();
		const bool cpuMatches = actualCpu == requestedCpu;
		const bool busMatches = actualBus == requestedBus || actualBus == requestedBus + 1 || actualBus == requestedBus - 1;
		PspClockStatus = PspClockApplyResult < 0 ? PspClockApplyStatus::ApplyFailed :
			(cpuMatches && busMatches ? PspClockApplyStatus::Ok : PspClockApplyStatus::Locked);
	}

	std::string PspAudioOptionsPath()
	{
		char* basePath = SDL_GetBasePath();
		std::string path = basePath ? basePath : "";
		if (basePath)
			SDL_free(basePath);
		path += "psp_options.cfg";
		return path;
	}

	void PspLoadAudioOptions()
	{
		auto path = PspAudioOptionsPath();
		auto rw = SDL_RWFromFile(path.c_str(), "rb");
		if (!rw)
		{
			PspApplyCpuClock();
			return;
		}

		const auto size = SDL_RWsize(rw);
		if (size > 0 && size < 256)
		{
			std::string data(static_cast<size_t>(size), '\0');
			const auto readCount =
				SDL_RWread(rw, &data[0], 1, static_cast<size_t>(size));

			if (readCount == static_cast<size_t>(size))
			{
				if (data.find("music=0") != std::string::npos)
					options::Options.Music = false;
				else if (data.find("music=1") != std::string::npos)
					options::Options.Music = true;

				if (data.find("sfx=0") != std::string::npos)
					options::Options.Sounds = false;
				else if (data.find("sfx=1") != std::string::npos)
					options::Options.Sounds = true;

				if (data.find("fps=0") != std::string::npos)
					PspShowFps = false;
				else if (data.find("fps=1") != std::string::npos)
					PspShowFps = true;

				if (data.find("benchmark=0") != std::string::npos)
					PspShowBenchmark = false;
				else if (data.find("benchmark=1") != std::string::npos)
					PspShowBenchmark = true;

				// FPS counter and benchmark overlay are mutually exclusive.
				// When migrating an old config with both enabled, keep BENCHMARK.
				if (PspShowBenchmark && PspShowFps)
					PspShowFps = false;

				if (data.find("cpu=222") != std::string::npos)
					PspCpuClockMHz = 222;
				else if (data.find("cpu=266") != std::string::npos)
					PspCpuClockMHz = 266;
				else if (data.find("cpu=300") != std::string::npos)
					PspCpuClockMHz = 300;
				else if (data.find("cpu=333") != std::string::npos)
					PspCpuClockMHz = 333;

				int videoProfile = std::max(0, std::min(1, static_cast<int>(options::Options.Resolution)));
				if (data.find("video=0") != std::string::npos)
					videoProfile = 0;
				// Migrate old PERFORMANCE/QUALITY 60 profiles to the single 60 FPS mode.
				else if (data.find("video=1") != std::string::npos ||
					data.find("video=2") != std::string::npos)
					videoProfile = 1;
				options::Options.Resolution = videoProfile;
				options::Options.FramesPerSecond = videoProfile == 0 ? 30 : 60;
			}
		}

		SDL_RWclose(rw);
		PspApplyCpuClock();
	}

	void PspSaveAudioOptions()
	{
		auto path = PspAudioOptionsPath();
		auto rw = SDL_RWFromFile(path.c_str(), "wb");
		if (!rw)
			return;

		std::string data =
			std::string("music=") +
			(static_cast<bool>(options::Options.Music) ? "1" : "0") +
			"\n" +
			"sfx=" +
			(static_cast<bool>(options::Options.Sounds) ? "1" : "0") +
			"\n" +
			"fps=" +
			(PspShowFps ? "1" : "0") +
			"\n" +
			"benchmark=" +
			(PspShowBenchmark ? "1" : "0") +
			"\n" +
			"cpu=" +
			std::to_string(PspCpuClockMHz) +
			"\n" +
			"video=" +
			std::to_string(std::max(0, std::min(1, static_cast<int>(options::Options.Resolution)))) +
			"\n";

		SDL_RWwrite(rw, data.data(), 1, data.size());
		SDL_RWclose(rw);
	}

	const Uint8* PspUiGlyph(char c)
	{
		static const Uint8 A[7] = {14,17,17,31,17,17,17};
		static const Uint8 B[7] = {30,17,17,30,17,17,30};
		static const Uint8 C[7] = {14,17,16,16,16,17,14};
		static const Uint8 D[7] = {30,17,17,17,17,17,30};
		static const Uint8 E[7] = {31,16,16,30,16,16,31};
		static const Uint8 F[7] = {31,16,16,30,16,16,16};
		static const Uint8 G[7] = {14,17,16,23,17,17,15};
		static const Uint8 H[7] = {17,17,17,31,17,17,17};
		static const Uint8 I[7] = {31,4,4,4,4,4,31};
		static const Uint8 J[7] = {7,2,2,2,18,18,12};
		static const Uint8 K[7] = {17,18,20,24,20,18,17};
		static const Uint8 L[7] = {16,16,16,16,16,16,31};
		static const Uint8 M[7] = {17,27,21,21,17,17,17};
		static const Uint8 N[7] = {17,25,21,19,17,17,17};
		static const Uint8 O[7] = {14,17,17,17,17,17,14};
		static const Uint8 P[7] = {30,17,17,30,16,16,16};
		static const Uint8 Q[7] = {14,17,17,17,21,18,13};
		static const Uint8 R[7] = {30,17,17,30,20,18,17};
		static const Uint8 S[7] = {15,16,16,14,1,1,30};
		static const Uint8 T[7] = {31,4,4,4,4,4,4};
		static const Uint8 U[7] = {17,17,17,17,17,17,14};
		static const Uint8 V[7] = {17,17,17,17,17,10,4};
		static const Uint8 W[7] = {17,17,17,21,21,21,10};
		static const Uint8 X[7] = {17,17,10,4,10,17,17};
		static const Uint8 Y[7] = {17,17,10,4,4,4,4};
		static const Uint8 Z[7] = {31,1,2,4,8,16,31};
		static const Uint8 D0[7] = {14,17,19,21,25,17,14};
		static const Uint8 D1[7] = {4,12,4,4,4,4,14};
		static const Uint8 D2[7] = {14,17,1,2,4,8,31};
		static const Uint8 D3[7] = {30,1,1,14,1,1,30};
		static const Uint8 D4[7] = {2,6,10,18,31,2,2};
		static const Uint8 D5[7] = {31,16,16,30,1,1,30};
		static const Uint8 D6[7] = {14,16,16,30,17,17,14};
		static const Uint8 D7[7] = {31,1,2,4,8,8,8};
		static const Uint8 D8[7] = {14,17,17,14,17,17,14};
		static const Uint8 D9[7] = {14,17,17,15,1,1,14};
		static const Uint8 Colon[7] = {0,4,4,0,4,4,0};
		static const Uint8 Greater[7] = {16,8,4,2,4,8,16};
		static const Uint8 Dot[7] = {0,0,0,0,0,4,4};
		static const Uint8 Percent[7] = {17,2,4,8,16,0,17};
		static const Uint8 Minus[7] = {0,0,0,31,0,0,0};
		static const Uint8 Blank[7] = {0,0,0,0,0,0,0};

		switch (c)
		{
		case 'A': return A; case 'B': return B; case 'C': return C;
		case 'D': return D; case 'E': return E; case 'F': return F;
		case 'G': return G; case 'H': return H; case 'I': return I;
		case 'J': return J; case 'K': return K; case 'L': return L;
		case 'M': return M; case 'N': return N; case 'O': return O;
		case 'P': return P; case 'Q': return Q; case 'R': return R;
		case 'S': return S; case 'T': return T; case 'U': return U;
		case 'V': return V; case 'W': return W; case 'X': return X;
		case 'Y': return Y; case 'Z': return Z;
		case '0': return D0; case '1': return D1; case '2': return D2;
		case '3': return D3; case '4': return D4; case '5': return D5;
		case '6': return D6; case '7': return D7; case '8': return D8;
		case '9': return D9;
		case ':': return Colon; case '>': return Greater; case '.': return Dot;
		case '%': return Percent; case '-': return Minus;
		default: return Blank;
		}
	}

	void PspDrawText(SDL_Renderer* renderer, int x, int y, const char* text, int scale)
	{
		const int charAdvance = 6 * scale;
		for (int ch = 0; text[ch] != 0; ++ch)
		{
			const auto glyph = PspUiGlyph(text[ch]);
			for (int row = 0; row < 7; ++row)
			{
				for (int col = 0; col < 5; ++col)
				{
					if (glyph[row] & (1 << (4 - col)))
					{
						SDL_Rect pixel{
							x + ch * charAdvance + col * scale,
							y + row * scale,
							scale,
							scale
						};
						SDL_RenderFillRect(renderer, &pixel);
					}
				}
			}
		}
	}

	void PspDrawFpsCounter(SDL_Renderer* renderer, int fps)
	{
		if (!renderer || !PspShowFps)
			return;

		fps = std::max(0, std::min(fps, 999));
		const std::string text = std::to_string(fps) + " FPS";

		SDL_BlendMode oldBlend = SDL_BLENDMODE_NONE;
		Uint8 oldR = 0, oldG = 0, oldB = 0, oldA = 255;
		SDL_Rect oldViewport{};
		SDL_bool oldClipEnabled = SDL_RenderIsClipEnabled(renderer);
		SDL_Rect oldClip{};

		SDL_GetRenderDrawBlendMode(renderer, &oldBlend);
		SDL_GetRenderDrawColor(renderer, &oldR, &oldG, &oldB, &oldA);
		SDL_RenderGetViewport(renderer, &oldViewport);
		if (oldClipEnabled)
			SDL_RenderGetClipRect(renderer, &oldClip);

		// Draw only inside the 44-pixel right pillarbox (x=436..479).
		SDL_RenderSetViewport(renderer, nullptr);
		SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_NONE);
		SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);

		const int len = static_cast<int>(text.size());
		const int textWidth = len > 0 ? (len - 1) * 6 + 5 : 0;
		const int x = std::max(437, 478 - textWidth + 1);
		PspDrawText(renderer, x, 4, text.c_str(), 1);

		SDL_RenderSetViewport(renderer, &oldViewport);
		if (oldClipEnabled)
			SDL_RenderSetClipRect(renderer, &oldClip);
		else
			SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawColor(renderer, oldR, oldG, oldB, oldA);
		SDL_SetRenderDrawBlendMode(renderer, oldBlend);
	}


	std::string PspFormatOneDecimal(double value)
	{
		char text[32];
		snprintf(text, sizeof(text), "%.1f", value);
		return text;
	}

	std::string PspFormatIntOrDash(int value)
	{
		return value >= 0 ? std::to_string(value) : "-";
	}

	void PspUpdateHardwareBenchmark()
	{
		PspBenchmark.cpuMHz = scePowerGetCpuClockFrequencyInt();
		PspBenchmark.busMHz = scePowerGetBusClockFrequencyInt();
		const int requestedBus = PspCpuClockMHz / 2;
		const bool cpuMatches = PspBenchmark.cpuMHz == PspCpuClockMHz;
		const bool busMatches = PspBenchmark.busMHz == requestedBus ||
			PspBenchmark.busMHz == requestedBus + 1 || PspBenchmark.busMHz == requestedBus - 1;
		PspClockStatus = PspClockApplyResult < 0 ? PspClockApplyStatus::ApplyFailed :
			(cpuMatches && busMatches ? PspClockApplyStatus::Ok : PspClockApplyStatus::Locked);
		PspBenchmark.freeMemKb = static_cast<unsigned>(sceKernelTotalFreeMemSize() / 1024);
		PspBenchmark.batteryPct = scePowerGetBatteryLifePercent();
		PspBenchmark.batteryTempC = scePowerGetBatteryTemp();
	}

	void PspDrawBenchmarkOverlay(SDL_Renderer* renderer)
	{
		if (!renderer || !PspShowBenchmark)
			return;

		SDL_BlendMode oldBlend = SDL_BLENDMODE_NONE;
		Uint8 oldR = 0, oldG = 0, oldB = 0, oldA = 255;
		SDL_Rect oldViewport{};
		SDL_bool oldClipEnabled = SDL_RenderIsClipEnabled(renderer);
		SDL_Rect oldClip{};
		SDL_GetRenderDrawBlendMode(renderer, &oldBlend);
		SDL_GetRenderDrawColor(renderer, &oldR, &oldG, &oldB, &oldA);
		SDL_RenderGetViewport(renderer, &oldViewport);
		if (oldClipEnabled)
			SDL_RenderGetClipRect(renderer, &oldClip);

		SDL_RenderSetViewport(renderer, nullptr);
		SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
		SDL_SetRenderDrawColor(renderer, 0, 0, 0, 190);
		SDL_Rect panel{304, 6, 170, 114};
		SDL_RenderFillRect(renderer, &panel);
		SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);

		const std::string lines[] = {
			"FPS " + std::to_string(PspBenchmark.fps) + " FRAME " + PspFormatOneDecimal(PspBenchmark.frameMs) + "MS",
			"CPU " + std::to_string(PspBenchmark.cpuMHz) + " BUS " + std::to_string(PspBenchmark.busMHz) + " " + PspClockStatusName(),
			"CPU EST " + PspFormatOneDecimal(PspBenchmark.cpuLoadPct) + "%",
			"GPU EST " + PspFormatOneDecimal(PspBenchmark.gpuLoadPct) + "%",
			"PHYS " + PspFormatOneDecimal(PspBenchmark.physicsMs) + "MS",
			"RENDER " + PspFormatOneDecimal(PspBenchmark.renderMs) + "MS",
			"PRESENT " + PspFormatOneDecimal(PspBenchmark.presentMs) + "MS",
			"FREE " + std::to_string(PspBenchmark.freeMemKb) + "KB",
			"BAT " + PspFormatIntOrDash(PspBenchmark.batteryPct) + "% TEMP " + PspFormatIntOrDash(PspBenchmark.batteryTempC) + "C"
		};
		for (int i = 0; i < 9; ++i)
			PspDrawText(renderer, 310, 12 + i * 12, lines[i].c_str(), 1);

		SDL_RenderSetViewport(renderer, &oldViewport);
		if (oldClipEnabled)
			SDL_RenderSetClipRect(renderer, &oldClip);
		else
			SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawColor(renderer, oldR, oldG, oldB, oldA);
		SDL_SetRenderDrawBlendMode(renderer, oldBlend);
	}

	Uint64 PspStartupBeginCounter = 0;
	Uint64 PspStartupLastCounter = 0;
	FILE* PspStartupLogFile = nullptr;

	void PspStartupBegin()
	{
		PspStartupBeginCounter = SDL_GetPerformanceCounter();
		PspStartupLastCounter = PspStartupBeginCounter;
		PspStartupLogFile = fopen("startup_profile.txt", "w");
		if (PspStartupLogFile) { fprintf(PspStartupLogFile, "Space Cadet Pinball PSP startup profile 0.5.6\n"); fflush(PspStartupLogFile); }
		printf("[startup] begin\n");
	}

	void PspStartupMark(const char* label)
	{
		const Uint64 now = SDL_GetPerformanceCounter();
		const double freq = static_cast<double>(SDL_GetPerformanceFrequency());
		const double deltaMs = (now - PspStartupLastCounter) * 1000.0 / freq;
		const double totalMs = (now - PspStartupBeginCounter) * 1000.0 / freq;
		printf("[startup] %-22s +%8.2f ms total=%8.2f ms\n", label, deltaMs, totalMs);
		if (PspStartupLogFile) { fprintf(PspStartupLogFile, "%-22s %8.2f ms total %8.2f ms\n", label, deltaMs, totalMs); fflush(PspStartupLogFile); }
		PspStartupLastCounter = now;
	}

	void PspStartupEnd()
	{
		PspStartupMark("startup complete");
		if (PspStartupLogFile) { fclose(PspStartupLogFile); PspStartupLogFile = nullptr; }
	}

	void PspShowLoadingScreen(SDL_Renderer* renderer)
	{
		if (!renderer)
			return;

		SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
		SDL_RenderClear(renderer);
		SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
		PspDrawText(renderer, 126, 122, "LOADING...", 4);
		SDL_RenderPresent(renderer);
		SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
	}

	const char* PspVideoProfileName(int profile)
	{
		switch (profile)
		{
		case 1: return "60 FPS";
		default: return "30 FPS";
		}
	}

	void PspDrawOptionsMenu(
		SDL_Renderer* renderer,
		bool musicEnabled,
		bool sfxEnabled,
		bool fpsEnabled,
		bool benchmarkEnabled,
		int videoProfile,
		int cpuClockMHz,
		int selection)
	{
		if (!renderer)
			return;

		SDL_BlendMode oldBlend = SDL_BLENDMODE_NONE;
		Uint8 oldR = 0, oldG = 0, oldB = 0, oldA = 255;
		SDL_Rect oldViewport{};
		SDL_bool oldClipEnabled = SDL_RenderIsClipEnabled(renderer);
		SDL_Rect oldClip{};

		SDL_GetRenderDrawBlendMode(renderer, &oldBlend);
		SDL_GetRenderDrawColor(renderer, &oldR, &oldG, &oldB, &oldA);
		SDL_RenderGetViewport(renderer, &oldViewport);
		if (oldClipEnabled)
			SDL_RenderGetClipRect(renderer, &oldClip);

		const SDL_Rect tableViewport{44, 0, 392, 272};
		SDL_RenderSetViewport(renderer, &tableViewport);
		SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
		SDL_SetRenderDrawColor(renderer, 0, 0, 0, 220);
		SDL_Rect panel{20, 18, 352, 238};
		SDL_RenderFillRect(renderer, &panel);

		SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
		PspDrawText(renderer, 124, 28, "OPTIONS", 3);
		PspDrawText(renderer, 54, 66, selection == 0 ? "> MUSIC:" : "  MUSIC:", 2);
		PspDrawText(renderer, 248, 66, musicEnabled ? "ON" : "OFF", 2);
		PspDrawText(renderer, 54, 92, selection == 1 ? "> SFX:" : "  SFX:", 2);
		PspDrawText(renderer, 248, 92, sfxEnabled ? "ON" : "OFF", 2);
		PspDrawText(renderer, 54, 118, selection == 2 ? "> FPS:" : "  FPS:", 2);
		PspDrawText(renderer, 248, 118, fpsEnabled ? "ON" : "OFF", 2);
		PspDrawText(renderer, 54, 144, selection == 3 ? "> VIDEO:" : "  VIDEO:", 2);
		PspDrawText(renderer, 248, 144, PspVideoProfileName(videoProfile), 2);
		PspDrawText(renderer, 54, 170, selection == 4 ? "> CPU:" : "  CPU:", 2);
		const std::string cpuText = std::to_string(cpuClockMHz) + " MHZ";
		PspDrawText(renderer, 248, 170, cpuText.c_str(), 2);
		PspDrawText(renderer, 54, 196, selection == 5 ? "> BENCHMARK:" : "  BENCHMARK:", 2);
		PspDrawText(renderer, 280, 196, benchmarkEnabled ? "ON" : "OFF", 2);
		PspDrawText(renderer, 86, 238, "TRIANGLE BACK    X SELECT", 1);

		SDL_RenderSetViewport(renderer, &oldViewport);
		if (oldClipEnabled) SDL_RenderSetClipRect(renderer, &oldClip);
		else SDL_RenderSetClipRect(renderer, nullptr);
		SDL_SetRenderDrawColor(renderer, oldR, oldG, oldB, oldA);
		SDL_SetRenderDrawBlendMode(renderer, oldBlend);
	}

	void PspSetMusicEnabled(bool enabled)
	{
		if (static_cast<bool>(options::Options.Music) != enabled)
		{
			options::toggle(Menu1::Music);
			PspSaveAudioOptions();
		}
	}

	void PspSetSfxEnabled(bool enabled)
	{
		if (static_cast<bool>(options::Options.Sounds) != enabled)
		{
			options::toggle(Menu1::Sounds);
			PspSaveAudioOptions();
		}
	}

	void PspSetFpsEnabled(bool enabled)
	{
		bool changed = false;
		if (enabled && PspShowBenchmark)
		{
			PspShowBenchmark = false;
			changed = true;
		}
		if (PspShowFps != enabled)
		{
			PspShowFps = enabled;
			changed = true;
		}
		if (changed)
			PspSaveAudioOptions();
	}


	void PspSetCpuClockProfile(int delta)
	{
		static const int clocks[] = {222, 266, 300, 333};
		int index = 3;
		for (int i = 0; i < 4; ++i)
		{
			if (clocks[i] == PspCpuClockMHz)
			{
				index = i;
				break;
			}
		}
		index = (index + delta) % 4;
		if (index < 0)
			index += 4;
		PspCpuClockMHz = clocks[index];
		PspApplyCpuClock();
		PspUpdateHardwareBenchmark();
		PspSaveAudioOptions();
	}

	void PspSetBenchmarkEnabled(bool enabled)
	{
		bool changed = false;
		if (enabled && PspShowFps)
		{
			PspShowFps = false;
			changed = true;
		}
		if (PspShowBenchmark != enabled)
		{
			PspShowBenchmark = enabled;
			changed = true;
		}
		if (enabled)
			PspUpdateHardwareBenchmark();
		if (changed)
			PspSaveAudioOptions();
	}

	void PspSetVideoProfile(int profile)
	{
		profile = (profile % 2 + 2) % 2;
		if (options::Options.Resolution == profile)
			return;
		options::Options.Resolution = profile;
		options::Options.FramesPerSecond = profile == 0 ? 30 : 60;
		PspSaveAudioOptions();
	}
}
#endif
