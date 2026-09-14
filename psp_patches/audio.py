import re
from .common import *

def patch_audio_assets(src):
    # PSP SFX bank: one Memory Stick read instead of 60 WAV opens.
    p = src / "SpaceCadetPinball" / "Sound.cpp"
    s = read(p)

    include_anchor = '#include "maths.h"\n'
    include_add = '''#ifdef SPACECADET_PSP
#include <unordered_map>
#include <cctype>
#include <cstring>
#endif
'''
    if include_add not in s:
        if include_anchor not in s:
            raise RuntimeError("Sound.cpp include anchor not found")
        s = s.replace(include_anchor, include_anchor + include_add, 1)

    bank_marker = "PSP_SFX_BANK_036"
    if bank_marker not in s:
        statics_anchor = "bool Sound::MixOpen = false;\n"
        if statics_anchor not in s:
            raise RuntimeError("Sound.cpp static anchor not found")

        bank_code = r'''
#ifdef SPACECADET_PSP
// PSP_SFX_BANK_036
namespace
{
    struct PspSfxBankEntry
    {
        Uint32 Offset;
        Uint32 Size;
    };

    std::vector<Uint8> PspSfxBankData;
    std::unordered_map<std::string, PspSfxBankEntry> PspSfxBankIndex;
    bool PspSfxBankAttempted = false;

    Uint32 PspReadLe32(const Uint8* p)
    {
        return static_cast<Uint32>(p[0]) |
            (static_cast<Uint32>(p[1]) << 8) |
            (static_cast<Uint32>(p[2]) << 16) |
            (static_cast<Uint32>(p[3]) << 24);
    }

    std::string PspSfxKey(const std::string& path)
    {
        auto slash = path.find_last_of("/\\\\");
        auto name = slash == std::string::npos ? path : path.substr(slash + 1);
        std::transform(name.begin(), name.end(), name.begin(),
            [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
        return name;
    }

    bool PspLoadSfxBank(const std::string& firstWavePath)
    {
        if (PspSfxBankAttempted)
            return !PspSfxBankData.empty();

        PspSfxBankAttempted = true;

        auto slash = firstWavePath.find_last_of("/\\\\");
        std::string bankPath =
            slash == std::string::npos
            ? "SFXBANK.BIN"
            : firstWavePath.substr(0, slash + 1) + "SFXBANK.BIN";

        auto file = fopenu(bankPath.c_str(), "rb");
        if (!file)
            return false;

        fseek(file, 0, SEEK_END);
        auto fileSizeLong = ftell(file);
        fseek(file, 0, SEEK_SET);

        if (fileSizeLong <= 12)
        {
            fclose(file);
            return false;
        }

        PspSfxBankData.resize(static_cast<size_t>(fileSizeLong));
        auto readSize = fread(PspSfxBankData.data(), 1, PspSfxBankData.size(), file);
        fclose(file);

        if (readSize != PspSfxBankData.size())
        {
            PspSfxBankData.clear();
            return false;
        }

        static const Uint8 Magic[8] = {'S','P','F','X','P','K','1',0};
        if (memcmp(PspSfxBankData.data(), Magic, 8) != 0)
        {
            PspSfxBankData.clear();
            return false;
        }

        auto count = PspReadLe32(PspSfxBankData.data() + 8);
        const size_t indexEnd = 12u + static_cast<size_t>(count) * 24u;
        if (indexEnd > PspSfxBankData.size())
        {
            PspSfxBankData.clear();
            return false;
        }

        for (Uint32 i = 0; i < count; ++i)
        {
            const auto pos = 12u + static_cast<size_t>(i) * 24u;
            const char* namePtr =
                reinterpret_cast<const char*>(PspSfxBankData.data() + pos);

            size_t nameLen = 0;
            while (nameLen < 16 && namePtr[nameLen] != 0)
                ++nameLen;

            std::string name(namePtr, nameLen);
            auto offset = PspReadLe32(PspSfxBankData.data() + pos + 16);
            auto size = PspReadLe32(PspSfxBankData.data() + pos + 20);

            if (offset > PspSfxBankData.size() ||
                size > PspSfxBankData.size() - offset)
            {
                PspSfxBankIndex.clear();
                PspSfxBankData.clear();
                return false;
            }

            PspSfxBankIndex[name] = {offset, size};
        }

        return true;
    }
}
#endif
'''
        s = s.replace(statics_anchor, statics_anchor + bank_code, 1)

    old_loader = '''Mix_Chunk* Sound::LoadWaveFile(const std::string& lpName)
{
    if (!MixOpen)
        return nullptr;

    auto wavFile = fopenu(lpName.c_str(), "r");
    if (!wavFile)
        return nullptr;
    fclose(wavFile);
    return Mix_LoadWAV(lpName.c_str());
}'''

    # Upstream uses tabs; fall back to structural replacement if exact text differs.
    fn_start = s.find("Mix_Chunk* Sound::LoadWaveFile(const std::string& lpName)")
    if fn_start < 0:
        raise RuntimeError("Sound.cpp LoadWaveFile not found")

    open_pos = s.find("{", fn_start)
    close_pos = find_matching_brace(s, open_pos)
    current_fn = s[fn_start:close_pos+1]

    if "PspLoadSfxBank(lpName)" not in current_fn:
        new_loader = r'''Mix_Chunk* Sound::LoadWaveFile(const std::string& lpName)
{
    if (!MixOpen)
        return nullptr;

#ifdef SPACECADET_PSP
    if (PspLoadSfxBank(lpName))
    {
        auto key = PspSfxKey(lpName);
        auto it = PspSfxBankIndex.find(key);
        if (it != PspSfxBankIndex.end())
        {
            const auto& entry = it->second;
            auto rw = SDL_RWFromConstMem(
                PspSfxBankData.data() + entry.Offset,
                static_cast<int>(entry.Size));

            if (rw)
                return Mix_LoadWAV_RW(rw, 1);
        }
    }
#endif

    auto wavFile = fopenu(lpName.c_str(), "r");
    if (!wavFile)
        return nullptr;
    fclose(wavFile);
    return Mix_LoadWAV(lpName.c_str());
}'''
        s = s[:fn_start] + new_loader + s[close_pos+1:]

    write(p, s)
    print("[ok]   PSP single-file SFX bank")

    # PSP music: user-generated low-CPU PCM WAV only. The clean package ships no music asset.
    p = src / "SpaceCadetPinball" / "midi.cpp"
    s = read(p)

    marker = "PSP_USER_MUSIC_072"
    if marker not in s:
        anchor = "Mix_Music* midi::load_track_sub(std::string fileName, bool isMidi)\n{\n"
        if anchor not in s:
            raise RuntimeError("midi.cpp load_track_sub anchor not found")

        addition = r'''#ifdef SPACECADET_PSP
    // PSP_USER_MUSIC_072: generated locally from user-owned original resources.
    // PCM WAV only: avoids compressed-audio decode overhead on PSP.
    if (isMidi && !pb::FullTiltMode)
    {
        auto musicName = fileName + ".WAV";
        for (int i = 0; i < 2; ++i)
        {
            if (i == 1)
                std::transform(musicName.begin(), musicName.end(), musicName.begin(),
                    [](unsigned char c) { return std::tolower(c); });
            auto filePath = pb::make_path_name(musicName);
            auto fileHandle = fopenu(filePath.c_str(), "rb");
            if (fileHandle)
            {
                fclose(fileHandle);
                auto rw = SDL_RWFromFile(filePath.c_str(), "rb");
                if (rw)
                {
                    auto music = Mix_LoadMUSType_RW(rw, MUS_WAV, 1);
                    if (music)
                        return music;
                }
            }
        }
        return nullptr;
    }
#endif
'''
        s = s.replace(anchor, anchor + addition, 1)

    write(p, s)
    print("[ok]   PSP user-generated low-CPU PCM WAV music")


def patch_sfx_direct_pcm(src):
    # Fast PSP path: convert bank WAV PCM directly to mixer PCM and bypass Mix_LoadWAV_RW.
    p = src / "SpaceCadetPinball" / "Sound.cpp"
    s = read(p)
    marker = "PSP_DIRECT_PCM_055"
    if marker in s:
        print("[skip] PSP direct PCM SFX conversion")
        return

    helper_anchor = """            PspSfxBankIndex[name] = {offset, size};
        }

        return true;
    }
}
#endif"""
    if s.count(helper_anchor) != 1:
        raise RuntimeError(f"Sound.cpp direct-PCM helper anchor mismatch: expected 1, found {s.count(helper_anchor)}")

    helper_replacement = r'''            PspSfxBankIndex[name] = {offset, size};
        }

        return true;
    }

    // PSP_DIRECT_PCM_055
    // The PSP SFX bank contains simple PCM WAVs. Convert directly to the
    // active mixer format instead of using SDL_mixer's generic WAV converter.
    std::unordered_map<Mix_Chunk*, Uint8*> PspSfxRawOwned;

    Uint16 PspReadLe16(const Uint8* p)
    {
        return static_cast<Uint16>(p[0]) |
            static_cast<Uint16>(static_cast<Uint16>(p[1]) << 8);
    }

    Mix_Chunk* PspQuickLoadBankPcm(const PspSfxBankEntry& entry)
    {
        if (entry.Offset > PspSfxBankData.size() ||
            entry.Size > PspSfxBankData.size() - entry.Offset || entry.Size < 44)
            return nullptr;

        const Uint8* wav = PspSfxBankData.data() + entry.Offset;
        const size_t wavSize = entry.Size;
        if (memcmp(wav, "RIFF", 4) != 0 || memcmp(wav + 8, "WAVE", 4) != 0)
            return nullptr;

        Uint16 waveFormat = 0, waveChannels = 0, bitsPerSample = 0;
        Uint32 waveRate = 0;
        const Uint8* pcm = nullptr;
        Uint32 pcmBytes = 0;

        size_t pos = 12;
        while (pos + 8 <= wavSize)
        {
            const Uint8* chunk = wav + pos;
            const Uint32 chunkSize = PspReadLe32(chunk + 4);
            const size_t payload = pos + 8;
            if (payload > wavSize || chunkSize > wavSize - payload)
                return nullptr;

            if (memcmp(chunk, "fmt ", 4) == 0 && chunkSize >= 16)
            {
                const Uint8* fmt = wav + payload;
                waveFormat = PspReadLe16(fmt + 0);
                waveChannels = PspReadLe16(fmt + 2);
                waveRate = PspReadLe32(fmt + 4);
                bitsPerSample = PspReadLe16(fmt + 14);
            }
            else if (memcmp(chunk, "data", 4) == 0)
            {
                pcm = wav + payload;
                pcmBytes = chunkSize;
            }

            const size_t next = payload + static_cast<size_t>(chunkSize) + (chunkSize & 1u);
            if (next <= pos)
                return nullptr;
            pos = next;
        }

        if (!pcm || !pcmBytes || waveFormat != 1 || waveChannels != 1 ||
            bitsPerSample != 8 || waveRate == 0)
            return nullptr;

        int outputRate = 0, outputChannels = 0;
        Uint16 outputFormat = 0;
        if (Mix_QuerySpec(&outputRate, &outputFormat, &outputChannels) <= 0 ||
            outputFormat != AUDIO_S16SYS || outputRate <= 0 ||
            (outputChannels != 1 && outputChannels != 2) ||
            outputRate < static_cast<int>(waveRate) ||
            outputRate % static_cast<int>(waveRate) != 0)
            return nullptr;

        const int rateRatio = outputRate / static_cast<int>(waveRate);
        if (rateRatio <= 0 || rateRatio > 16)
            return nullptr;

        const size_t outputFrames = static_cast<size_t>(pcmBytes) * static_cast<size_t>(rateRatio);
        const size_t outputSamples = outputFrames * static_cast<size_t>(outputChannels);
        const size_t outputBytes = outputSamples * sizeof(Sint16);
        if (!outputBytes || outputBytes > 0xffffffffu)
            return nullptr;

        auto raw = static_cast<Uint8*>(SDL_malloc(outputBytes));
        if (!raw)
            return nullptr;
        auto dst = reinterpret_cast<Sint16*>(raw);

        size_t dstIndex = 0;
        for (Uint32 i = 0; i < pcmBytes; ++i)
        {
            const Sint16 sample = static_cast<Sint16>((static_cast<int>(pcm[i]) - 128) * 256);
            for (int repeat = 0; repeat < rateRatio; ++repeat)
            {
                dst[dstIndex++] = sample;
                if (outputChannels == 2)
                    dst[dstIndex++] = sample;
            }
        }

        auto wave = Mix_QuickLoad_RAW(raw, static_cast<Uint32>(outputBytes));
        if (!wave)
        {
            SDL_free(raw);
            return nullptr;
        }

        PspSfxRawOwned[wave] = raw;
        return wave;
    }
}
#endif'''
    s = s.replace(helper_anchor, helper_replacement, 1)

    load_anchor = r'''        if (it != PspSfxBankIndex.end())
        {
            const auto& entry = it->second;
            auto rw = SDL_RWFromConstMem(
                PspSfxBankData.data() + entry.Offset,
                static_cast<int>(entry.Size));

            if (rw)
                return Mix_LoadWAV_RW(rw, 1);
        }'''
    load_replacement = r'''        if (it != PspSfxBankIndex.end())
        {
            const auto& entry = it->second;
            if (auto fastWave = PspQuickLoadBankPcm(entry))
                return fastWave;

            // Compatibility fallback for an unexpected WAV format.
            auto rw = SDL_RWFromConstMem(
                PspSfxBankData.data() + entry.Offset,
                static_cast<int>(entry.Size));
            if (rw)
                return Mix_LoadWAV_RW(rw, 1);
        }'''
    if s.count(load_anchor) != 1:
        raise RuntimeError(f"Sound.cpp bank-load anchor mismatch: expected 1, found {s.count(load_anchor)}")
    s = s.replace(load_anchor, load_replacement, 1)

    fn_start = s.find("void Sound::FreeSound(Mix_Chunk* wave)")
    if fn_start < 0:
        raise RuntimeError("Sound.cpp FreeSound not found")
    fn_open = s.find("{", fn_start)
    fn_close = find_matching_brace(s, fn_open)
    if fn_open < 0 or fn_close < 0:
        raise RuntimeError("Sound.cpp FreeSound braces not found")

    free_replacement = r'''void Sound::FreeSound(Mix_Chunk* wave)
{
    if (MixOpen && wave)
    {
#ifdef SPACECADET_PSP
        auto owned = PspSfxRawOwned.find(wave);
        if (owned != PspSfxRawOwned.end())
        {
            auto raw = owned->second;
            PspSfxRawOwned.erase(owned);
            Mix_FreeChunk(wave);
            SDL_free(raw);
            return;
        }
#endif
        Mix_FreeChunk(wave);
    }
}'''
    s = s[:fn_start] + free_replacement + s[fn_close + 1:]

    write(p, s)
    print("[ok]   PSP direct PCM SFX conversion (bypass Mix_LoadWAV_RW)")


def patch_sfx_fast_lookup(src):
    """Avoid per-sound missing-WAV probes on PSP when SFXBANK.BIN is used."""
    p = src / "SpaceCadetPinball" / "loader.cpp"
    s = read(p)
    marker = "PSP_FAST_SFX_LOOKUP_054"
    if marker in s:
        print("[skip] PSP fast SFX bank lookup/duration")
        return

    fn_start = s.find("int loader::get_sound_id(int groupIndex)")
    if fn_start < 0:
        raise RuntimeError("loader.cpp get_sound_id not found")
    fn_open = s.find("{", fn_start)
    fn_close = find_matching_brace(s, fn_open)
    if fn_open < 0 or fn_close < 0:
        raise RuntimeError("loader.cpp get_sound_id braces not found")

    block_start = s.find("std::string filePath;", fn_open, fn_close)
    block_end_token = "sound_list[soundIndex].WavePtr = Sound::LoadWaveFile(filePath);"
    block_end = s.find(block_end_token, block_start, fn_close)
    if block_start < 0 or block_end < 0:
        raise RuntimeError("loader.cpp PSP fast-SFX anchor not found")

    line_start = s.rfind("\n", fn_open, block_start) + 1
    end_line = s.find("\n", block_end + len(block_end_token), fn_close)
    if end_line < 0:
        end_line = block_end + len(block_end_token)
    original = s[line_start:end_line]
    indent = s[line_start:block_start]

    lines = [
        indent + "// PSP_FAST_SFX_LOOKUP_054",
        indent + "#ifdef SPACECADET_PSP",
        indent + "std::string filePath = pb::make_path_name(fileName);",
        indent + "auto wave = Sound::LoadWaveFile(filePath);",
        indent + "if (!wave)",
        indent + "{",
        indent + "\t// Keep the upstream uppercase fallback for loose-WAV compatibility.",
        indent + "\tstd::transform(fileName.begin(), fileName.end(), fileName.begin(),",
        indent + "\t               [](unsigned char c) { return std::toupper(c); });",
        indent + "\tfilePath = pb::make_path_name(fileName);",
        indent + "\twave = Sound::LoadWaveFile(filePath);",
        indent + "}",
        indent + "sound_list[soundIndex].WavePtr = wave;",
        indent + "float duration = -1.0f;",
        indent + "if (wave)",
        indent + "{",
        indent + "\tint frequency = 0;",
        indent + "\tint channels = 0;",
        indent + "\tUint16 format = 0;",
        indent + "\tif (Mix_QuerySpec(&frequency, &format, &channels) > 0 && frequency > 0 && channels > 0)",
        indent + "\t{",
        indent + "\t\tconst int bytesPerSample = SDL_AUDIO_BITSIZE(format) / 8;",
        indent + "\t\tif (bytesPerSample > 0)",
        indent + "\t\t{",
        indent + "\t\t\tconst double bytesPerSecond = static_cast<double>(frequency) * channels * bytesPerSample;",
        indent + "\t\t\tduration = static_cast<float>(static_cast<double>(wave->alen) / bytesPerSecond);",
        indent + "\t\t}",
        indent + "\t}",
        indent + "}",
        indent + "sound_list[soundIndex].Duration = duration;",
        indent + "#else",
        original,
        indent + "#endif",
    ]
    replacement = "\n".join(lines)
    s = s[:line_start] + replacement + s[end_line:]
    write(p, s)
    print("[ok]   PSP fast SFX bank lookup/duration (no missing WAV probes)")


