from .common import read, write, find_matching_brace

HELPER = r'''
#ifdef SPACECADET_PSP
// PSP_PCM_MUSIC_STREAMER
namespace
{
    FILE* PspMusicFile = nullptr;
    long PspMusicDataOffset = 0;
    Uint32 PspMusicDataBytes = 0;
    Uint32 PspMusicDataPosition = 0;
    Sint16 PspMusicBuffer[2048]{};
    size_t PspMusicBufferCount = 0;
    size_t PspMusicBufferPosition = 0;
    Sint16 PspMusicCurrentSample = 0;
    int PspMusicRepeatPhase = 0;
    bool PspMusicHookInstalled = false;
    int PspMusicVolume = MIX_MAX_VOLUME;

    Uint16 PspMusicReadLe16(const Uint8* p)
    {
        return static_cast<Uint16>(p[0]) |
            static_cast<Uint16>(static_cast<Uint16>(p[1]) << 8);
    }

    Uint32 PspMusicReadLe32(const Uint8* p)
    {
        return static_cast<Uint32>(p[0]) |
            (static_cast<Uint32>(p[1]) << 8) |
            (static_cast<Uint32>(p[2]) << 16) |
            (static_cast<Uint32>(p[3]) << 24);
    }

    void PspCloseMusicFile()
    {
        if (PspMusicHookInstalled)
        {
            Mix_HookMusic(nullptr, nullptr);
            PspMusicHookInstalled = false;
        }
        if (PspMusicFile)
        {
            fclose(PspMusicFile);
            PspMusicFile = nullptr;
        }
        PspMusicDataOffset = 0;
        PspMusicDataBytes = 0;
        PspMusicDataPosition = 0;
        PspMusicBufferCount = 0;
        PspMusicBufferPosition = 0;
        PspMusicCurrentSample = 0;
        PspMusicRepeatPhase = 0;
    }

    bool PspOpenMusicFile(const std::string& filePath)
    {
        PspCloseMusicFile();
        auto file = fopenu(filePath.c_str(), "rb");
        if (!file)
            return false;

        Uint8 riff[12]{};
        if (fread(riff, 1, sizeof(riff), file) != sizeof(riff) ||
            memcmp(riff, "RIFF", 4) != 0 || memcmp(riff + 8, "WAVE", 4) != 0)
        {
            fclose(file);
            return false;
        }

        Uint16 format = 0, channels = 0, bits = 0;
        Uint32 rate = 0, dataBytes = 0;
        long dataOffset = 0;
        while (true)
        {
            Uint8 header[8]{};
            if (fread(header, 1, sizeof(header), file) != sizeof(header))
                break;
            const Uint32 chunkSize = PspMusicReadLe32(header + 4);
            const long payload = ftell(file);
            if (memcmp(header, "fmt ", 4) == 0 && chunkSize >= 16)
            {
                Uint8 fmt[16]{};
                if (fread(fmt, 1, sizeof(fmt), file) != sizeof(fmt))
                    break;
                format = PspMusicReadLe16(fmt + 0);
                channels = PspMusicReadLe16(fmt + 2);
                rate = PspMusicReadLe32(fmt + 4);
                bits = PspMusicReadLe16(fmt + 14);
            }
            else if (memcmp(header, "data", 4) == 0)
            {
                dataOffset = payload;
                dataBytes = chunkSize;
                break;
            }
            if (fseek(file, payload + static_cast<long>(chunkSize + (chunkSize & 1u)), SEEK_SET) != 0)
                break;
        }

        if (format != 1 || channels != 1 || rate != 22050 || bits != 16 ||
            dataOffset <= 0 || dataBytes < 2)
        {
            fclose(file);
            return false;
        }

        PspMusicFile = file;
        PspMusicDataOffset = dataOffset;
        PspMusicDataBytes = dataBytes & ~1u;
        PspMusicDataPosition = 0;
        PspMusicBufferCount = 0;
        PspMusicBufferPosition = 0;
        PspMusicRepeatPhase = 0;
        fseek(PspMusicFile, PspMusicDataOffset, SEEK_SET);
        return true;
    }

    bool PspRefillMusicBuffer()
    {
        if (!PspMusicFile || PspMusicDataBytes < 2)
            return false;
        if (PspMusicDataPosition >= PspMusicDataBytes)
        {
            PspMusicDataPosition = 0;
            fseek(PspMusicFile, PspMusicDataOffset, SEEK_SET);
        }
        const Uint32 bytesLeft = PspMusicDataBytes - PspMusicDataPosition;
        const size_t samplesWanted = std::min<size_t>(2048, bytesLeft / 2u);
        const size_t samplesRead = fread(PspMusicBuffer, sizeof(Sint16), samplesWanted, PspMusicFile);
        if (!samplesRead)
        {
            clearerr(PspMusicFile);
            PspMusicDataPosition = 0;
            fseek(PspMusicFile, PspMusicDataOffset, SEEK_SET);
            const size_t retry = fread(PspMusicBuffer, sizeof(Sint16), 2048, PspMusicFile);
            if (!retry)
                return false;
            PspMusicBufferCount = retry;
            PspMusicDataPosition = static_cast<Uint32>(retry * sizeof(Sint16));
        }
        else
        {
            PspMusicBufferCount = samplesRead;
            PspMusicDataPosition += static_cast<Uint32>(samplesRead * sizeof(Sint16));
        }
        PspMusicBufferPosition = 0;
        return true;
    }

    bool PspNextMusicSample(Sint16& sample)
    {
        if (PspMusicBufferPosition >= PspMusicBufferCount && !PspRefillMusicBuffer())
            return false;
        sample = PspMusicBuffer[PspMusicBufferPosition++];
        return true;
    }

    void PspMusicCallback(void*, Uint8* stream, int len)
    {
        memset(stream, 0, static_cast<size_t>(len));
        auto output = reinterpret_cast<Sint16*>(stream);
        const int frames = len / static_cast<int>(sizeof(Sint16) * 2);
        for (int frame = 0; frame < frames; ++frame)
        {
            if (PspMusicRepeatPhase == 0 && !PspNextMusicSample(PspMusicCurrentSample))
                break;
            const int scaled = (static_cast<int>(PspMusicCurrentSample) * PspMusicVolume) / MIX_MAX_VOLUME;
            const auto sample = static_cast<Sint16>(std::max(-32768, std::min(32767, scaled)));
            output[frame * 2 + 0] = sample;
            output[frame * 2 + 1] = sample;
            PspMusicRepeatPhase ^= 1;
        }
    }
}
#endif
'''

def _replace_function(s, signature, psp_body):
    start = s.find(signature)
    if start < 0:
        raise RuntimeError(f"midi.cpp function not found: {signature}")
    op = s.find("{", start)
    cl = find_matching_brace(s, op)
    old = s[start:cl + 1]
    original_body = old[old.find("{") + 1:-1]
    new = signature + "\n{\n#ifdef SPACECADET_PSP\n" + psp_body + "\n#else\n" + original_body + "\n#endif\n}"
    return s[:start] + new + s[cl + 1:]

def patch_psp_pcm_music_streamer(src):
    p = src / "SpaceCadetPinball" / "midi.cpp"
    s = read(p)
    if "PSP_PCM_MUSIC_STREAMER" in s:
        print("[skip] PSP PCM music streamer")
        return

    anchor = "bool midi::IsPlaying = false, midi::MixOpen = false;\n"
    if s.count(anchor) != 1:
        raise RuntimeError("midi.cpp streamer static anchor mismatch")
    s = s.replace(anchor, anchor + HELPER, 1)

    init_body = r'''    MixOpen = mixOpen;
    SetVolume(volume);
    active_track = MidiTracks::None;
    NextTrack = MidiTracks::None;
    IsPlaying = false;
    track1 = track2 = track3 = nullptr;
    if (!MixOpen || pb::FullTiltMode)
        return false;
    for (int i = 0; i < 2; ++i)
    {
        std::string name = i == 0 ? "PINBALL.WAV" : "pinball.wav";
        if (PspOpenMusicFile(pb::make_path_name(name)))
        {
            track1 = reinterpret_cast<Mix_Music*>(1);
            return true;
        }
    }
    return false;'''
    s = _replace_function(s, "int midi::music_init(bool mixOpen, int volume)", init_body)

    shutdown_body = r'''    music_stop();
    PspCloseMusicFile();
    track1 = track2 = track3 = nullptr;
    LoadedTracks.clear();'''
    s = _replace_function(s, "void midi::music_shutdown()", shutdown_body)

    stop_body = r'''    if (PspMusicHookInstalled)
    {
        Mix_HookMusic(nullptr, nullptr);
        PspMusicHookInstalled = false;
    }
    active_track = MidiTracks::None;'''
    s = _replace_function(s, "void midi::StopPlayback()", stop_body)

    play_body = r'''    if (track != MidiTracks::Track1 || !track1 || (!replay && active_track == track))
        return false;
    StopPlayback();
    if (!IsPlaying)
    {
        NextTrack = track;
        return false;
    }
    if (!PspMusicFile)
        return false;
    PspMusicDataPosition = 0;
    PspMusicBufferCount = 0;
    PspMusicBufferPosition = 0;
    PspMusicRepeatPhase = 0;
    fseek(PspMusicFile, PspMusicDataOffset, SEEK_SET);
    Mix_HookMusic(PspMusicCallback, nullptr);
    PspMusicHookInstalled = true;
    active_track = track;
    SetVolume(Volume);
    return true;'''
    s = _replace_function(s, "bool midi::play_track(MidiTracks track, bool replay)", play_body)

    volume_body = r'''    Volume = std::max(0, std::min(MIX_MAX_VOLUME, volume));
    PspMusicVolume = Volume;'''
    s = _replace_function(s, "void midi::SetVolume(int volume)", volume_body)

    write(p, s)
    print("[ok]   PSP custom PCM music streamer (22050 mono -> 44100 stereo)")
