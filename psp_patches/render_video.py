import re
from .common import *

def patch_renderer(src):
    p = src / "SpaceCadetPinball" / "render.cpp"

    helper = r'''
#ifdef SPACECADET_PSP
namespace
{
	constexpr int PspTextureSplitX = 512;
	SDL_Texture* PspVScreenLeft = nullptr;
	SDL_Texture* PspVScreenRight = nullptr;
	int PspLeftWidth = 0;
	int PspRightWidth = 0;
	int PspScreenHeight = 0;

	void PspDestroyVScreenTextures()
	{
		if (PspVScreenLeft) SDL_DestroyTexture(PspVScreenLeft);
		if (PspVScreenRight) SDL_DestroyTexture(PspVScreenRight);
		PspVScreenLeft = nullptr;
		PspVScreenRight = nullptr;
		PspLeftWidth = PspRightWidth = PspScreenHeight = 0;
	}

	SDL_Texture* PspCreateVScreenTexture(int width, int height)
	{
		if (width <= 0 || height <= 0 || width > 512 || height > 512)
			return nullptr;
		SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
		auto texture = SDL_CreateTexture(
			winmain::Renderer, SDL_PIXELFORMAT_BGR565,
			SDL_TEXTUREACCESS_STREAMING, width, height);
		if (texture)
			SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_NONE);
		return texture;
	}

	// PSP_BGR565_PRESENT_043
	// SDL's PSP renderer maps SDL_PIXELFORMAT_BGR565 directly to GU_PSM_5650.
	// The game compositor remains 32-bit ColorRgba; only pixels being uploaded
	// are packed into a reusable 16-bit staging buffer.
	std::vector<uint16_t> PspUploadBuffer565;

	uint16_t PspPackBgr565(const ColorRgba& pixel)
	{
		return static_cast<uint16_t>(
			(static_cast<uint16_t>(pixel.GetBlue() >> 3) << 11) |
			(static_cast<uint16_t>(pixel.GetGreen() >> 2) << 5) |
			 static_cast<uint16_t>(pixel.GetRed() >> 3));
	}

	bool PspUploadConvertedRect(SDL_Texture* texture, int segmentX, int segmentWidth,
	                            gdrv_bitmap8* screen, const SDL_Rect& dirty)
	{
		if (!texture || segmentWidth <= 0)
			return true;

		const int x0 = std::max(dirty.x, segmentX);
		const int x1 = std::min(dirty.x + dirty.w, segmentX + segmentWidth);
		const int y0 = std::max(0, dirty.y);
		const int y1 = std::min(screen->Height, dirty.y + dirty.h);
		if (x1 <= x0 || y1 <= y0)
			return true;

		const int width = x1 - x0;
		const int height = y1 - y0;
		const size_t pixelCount = static_cast<size_t>(width) * height;
		PspUploadBuffer565.resize(pixelCount);

		for (int row = 0; row < height; ++row)
		{
			const auto* src = screen->BmpBufPtr1 + (y0 + row) * screen->Stride + x0;
			auto* dst = PspUploadBuffer565.data() + static_cast<size_t>(row) * width;
			for (int col = 0; col < width; ++col)
				dst[col] = PspPackBgr565(src[col]);
		}

		SDL_Rect localRect{x0 - segmentX, y0, width, height};
		const int pitch565 = width * static_cast<int>(sizeof(uint16_t));
		return SDL_UpdateTexture(texture, &localRect, PspUploadBuffer565.data(), pitch565) == 0;
	}

	bool PspUploadVScreen(gdrv_bitmap8* screen)
	{
		if (!screen || !PspVScreenLeft)
			return false;

		SDL_Rect fullRect{0, 0, screen->Width, screen->Height};
		return PspUploadConvertedRect(PspVScreenLeft, 0, PspLeftWidth, screen, fullRect) &&
		       PspUploadConvertedRect(PspVScreenRight, PspLeftWidth, PspRightWidth, screen, fullRect);
	}

	void PspRenderLogicalRange(int logicalX, int logicalWidth, const SDL_Rect& destination)
	{
		if (logicalWidth <= 0 || destination.w <= 0 || destination.h <= 0)
			return;

		struct Segment { SDL_Texture* texture; int logicalX; int width; };
		const Segment segments[2] = {
			{PspVScreenLeft, 0, PspLeftWidth},
			{PspVScreenRight, PspLeftWidth, PspRightWidth}
		};

		const int logicalEnd = logicalX + logicalWidth;
		for (const auto& segment : segments)
		{
			if (!segment.texture || segment.width <= 0)
				continue;

			const int segEnd = segment.logicalX + segment.width;
			const int x0 = std::max(logicalX, segment.logicalX);
			const int x1 = std::min(logicalEnd, segEnd);
			if (x1 <= x0)
				continue;

			SDL_Rect src{x0 - segment.logicalX, 0, x1 - x0, PspScreenHeight};
			const double t0 = static_cast<double>(x0 - logicalX) / logicalWidth;
			const double t1 = static_cast<double>(x1 - logicalX) / logicalWidth;
			const int dstX0 = destination.x + static_cast<int>(std::round(destination.w * t0));
			const int dstX1 = destination.x + static_cast<int>(std::round(destination.w * t1));
			SDL_Rect dst{dstX0, destination.y, std::max(1, dstX1 - dstX0), destination.h};

			SDL_RenderCopy(winmain::Renderer, segment.texture, &src, &dst);
		}
	}
}
#endif
'''
    insert_after_once(p, "SDL_Rect render::DestinationRect{};\n", helper, "PSP split-texture helpers")

    insert_after_once(
        p,
        "void render::uninit()\n{\n",
        '''#ifdef SPACECADET_PSP
\tPspDestroyVScreenTextures();
#endif
''',
        "destroy PSP presentation textures"
    )

    replace_once(
        p,
        '''void render::recreate_screen_texture()
{
\tvscreen->CreateTexture(options::Options.LinearFiltering ? "linear" : "nearest", SDL_TEXTUREACCESS_STREAMING);
}''',
        '''void render::recreate_screen_texture()
{
#ifdef SPACECADET_PSP
\tPspDestroyVScreenTextures();
\tPspLeftWidth = std::min(vscreen->Width, PspTextureSplitX);
\tPspRightWidth = vscreen->Width - PspLeftWidth;
\tPspScreenHeight = vscreen->Height;

\tif (PspRightWidth > 512 || PspScreenHeight > 512)
\t{
\t\tprintf("PSP: unsupported logical surface %dx%d\\n", vscreen->Width, vscreen->Height);
\t\treturn;
\t}

\tPspVScreenLeft = PspCreateVScreenTexture(PspLeftWidth, PspScreenHeight);
\tif (PspRightWidth > 0)
\t\tPspVScreenRight = PspCreateVScreenTexture(PspRightWidth, PspScreenHeight);

\tif (!PspVScreenLeft || (PspRightWidth > 0 && !PspVScreenRight))
\t\tprintf("PSP: failed to create split vscreen textures: %s\\n", SDL_GetError());
#else
\tvscreen->CreateTexture(options::Options.LinearFiltering ? "linear" : "nearest", SDL_TEXTUREACCESS_STREAMING);
#endif
}''',
        "PSP split-texture creation"
    )

    s = read(p)
    render_marker = "PSP_SPLIT_PRESENT_030"
    if render_marker not in s:
        fn_pos = s.find("void render::PresentVScreen()")
        if fn_pos < 0:
            raise RuntimeError("render.cpp: PresentVScreen not found")
        open_pos = s.find("{", fn_pos)
        close_pos = find_matching_brace(s, open_pos)
        original_body = s[open_pos + 1:close_pos]
        psp_prefix = r'''
#ifdef SPACECADET_PSP
    // PSP_SPLIT_PRESENT_030
    if (!PspUploadVScreen(vscreen))
    {
        printf("PSP: vscreen upload failed: %s\\n", SDL_GetError());
        return;
    }

    if (offset_x == 0 && offset_y == 0)
    {
        PspRenderLogicalRange(0, vscreen->Width, DestinationRect);
    }
    else
    {
        const auto coef = static_cast<float>(pb::MainTable->Width) / vscreen->Width;
        const auto srcSplit = static_cast<int>(std::round(vscreen->Width * coef));
        const auto dstSplit = static_cast<int>(std::round(DestinationRect.w * coef));

        auto offX = static_cast<int>(std::round(offset_x * fullscrn::ScaleX));
        auto offY = static_cast<int>(std::round(offset_y * fullscrn::ScaleY));
        if (offset_x && offX == 0) offX = offset_x > 0 ? 1 : -1;
        if (offset_y && offY == 0) offY = offset_y > 0 ? 1 : -1;

        SDL_Rect boardDst{DestinationRect.x + offX, DestinationRect.y + offY, dstSplit, DestinationRect.h};
        SDL_Rect sidebarDst{DestinationRect.x + dstSplit, DestinationRect.y, DestinationRect.w - dstSplit, DestinationRect.h};
        PspRenderLogicalRange(0, srcSplit, boardDst);
        PspRenderLogicalRange(srcSplit, vscreen->Width - srcSplit, sidebarDst);
    }
    if (options::Options.DebugOverlay)
        DebugOverlay::DrawOverlay();
#else
'''
        replacement = s[fn_pos:open_pos + 1] + psp_prefix + original_body + "\n#endif\n}"
        s = s[:fn_pos] + replacement + s[close_pos + 1:]
        write(p, s)
        print("[ok]   PSP split-texture presentation (structural)")
    else:
        print("[skip] PSP split-texture presentation")


def patch_dirty_upload(src):
    # PSP 0.4.3: keep the native 600x416 BGRA32 CPU compositor, but only
    # convert/upload portions of vScreen that changed since last present.
    p = src / "SpaceCadetPinball" / "render.cpp"

    insert_after_once(
        p,
        "\tint PspScreenHeight = 0;\n",
        r'''
	// PSP_DIRTY_UPLOAD_040
	// Accumulates compositor changes across 120 Hz physics updates until the
	// next 30 Hz presentation. Large/fragmented updates fall back to full.
	constexpr int PspMaxDirtyRects = 24;
	std::vector<SDL_Rect> PspDirtyRects;
	bool PspFullUploadPending = true;

	bool PspRectsTouch(const SDL_Rect& a, const SDL_Rect& b)
	{
		constexpr int pad = 2;
		return a.x <= b.x + b.w + pad && b.x <= a.x + a.w + pad &&
		       a.y <= b.y + b.h + pad && b.y <= a.y + a.h + pad;
	}

	SDL_Rect PspUnionRect(const SDL_Rect& a, const SDL_Rect& b)
	{
		const int x0 = std::min(a.x, b.x);
		const int y0 = std::min(a.y, b.y);
		const int x1 = std::max(a.x + a.w, b.x + b.w);
		const int y1 = std::max(a.y + a.h, b.y + b.h);
		return SDL_Rect{x0, y0, x1 - x0, y1 - y0};
	}

	void PspMarkDirtyRect(int x, int y, int width, int height)
	{
		if (PspFullUploadPending || width <= 0 || height <= 0 ||
		    PspLeftWidth + PspRightWidth <= 0 || PspScreenHeight <= 0)
			return;

		const int screenWidth = PspLeftWidth + PspRightWidth;
		const int x0 = std::max(0, x);
		const int y0 = std::max(0, y);
		const int x1 = std::min(screenWidth, x + width);
		const int y1 = std::min(PspScreenHeight, y + height);
		if (x1 <= x0 || y1 <= y0)
			return;

		SDL_Rect merged{x0, y0, x1 - x0, y1 - y0};
		for (size_t i = 0; i < PspDirtyRects.size();)
		{
			if (PspRectsTouch(merged, PspDirtyRects[i]))
			{
				merged = PspUnionRect(merged, PspDirtyRects[i]);
				PspDirtyRects.erase(PspDirtyRects.begin() + i);
				i = 0;
			}
			else
			{
				++i;
			}
		}

		if (static_cast<int>(PspDirtyRects.size()) >= PspMaxDirtyRects)
		{
			PspDirtyRects.clear();
			PspFullUploadPending = true;
			return;
		}
		PspDirtyRects.push_back(merged);
	}
''',
        "PSP dirty upload state"
    )

    replace_once(
        p,
        '''\t\tPspVScreenLeft = nullptr;\n\t\tPspVScreenRight = nullptr;\n\t\tPspLeftWidth = PspRightWidth = PspScreenHeight = 0;''',
        '''\t\tPspVScreenLeft = nullptr;\n\t\tPspVScreenRight = nullptr;\n\t\tPspLeftWidth = PspRightWidth = PspScreenHeight = 0;\n\t\tPspDirtyRects.clear();\n\t\tPspFullUploadPending = true;''',
        "reset PSP dirty upload state"
    )

    old_upload = '''	bool PspUploadVScreen(gdrv_bitmap8* screen)
	{
		if (!screen || !PspVScreenLeft)
			return false;

		SDL_Rect fullRect{0, 0, screen->Width, screen->Height};
		return PspUploadConvertedRect(PspVScreenLeft, 0, PspLeftWidth, screen, fullRect) &&
		       PspUploadConvertedRect(PspVScreenRight, PspLeftWidth, PspRightWidth, screen, fullRect);
	}
'''
    new_upload = '''	bool PspUploadVScreen(gdrv_bitmap8* screen)
	{
		if (!screen || !PspVScreenLeft)
			return false;

		const int fullArea = screen->Width * screen->Height;
		int dirtyArea = 0;
		for (const auto& rect : PspDirtyRects)
			dirtyArea += rect.w * rect.h;

		const bool uploadFull = PspFullUploadPending ||
		    dirtyArea >= (fullArea * 3) / 5;

		if (uploadFull)
		{
			SDL_Rect fullRect{0, 0, screen->Width, screen->Height};
			if (!PspUploadConvertedRect(PspVScreenLeft, 0, PspLeftWidth, screen, fullRect) ||
			    !PspUploadConvertedRect(PspVScreenRight, PspLeftWidth, PspRightWidth, screen, fullRect))
				return false;
		}
		else
		{
			for (const auto& rect : PspDirtyRects)
			{
				if (!PspUploadConvertedRect(PspVScreenLeft, 0, PspLeftWidth, screen, rect) ||
				    !PspUploadConvertedRect(PspVScreenRight, PspLeftWidth, PspRightWidth, screen, rect))
				{
					PspFullUploadPending = true;
					return false;
				}
			}
		}

		PspDirtyRects.clear();
		PspFullUploadPending = false;
		return true;
	}
'''
    replace_once(p, old_upload, new_upload, "PSP dirty/partial texture upload")

    # Track compositor changes structurally inside each render function.
    # Avoid whole-block anchors here: patch_render() has already transformed
    # render.cpp earlier in this same run.
    s = read(p)

    sprite_marker = "PspMarkDirtyRect(sprite->DirtyRect.XPosition"
    if sprite_marker not in s:
        fn_pos = s.find("void render::update()")
        if fn_pos < 0:
            raise RuntimeError("render.cpp: render::update not found for PSP dirty tracking")
        fn_open = s.find("{", fn_pos)
        fn_close = find_matching_brace(s, fn_open)
        clear_pos = s.find("if (clearSprite)", fn_open, fn_close)
        if clear_pos < 0:
            raise RuntimeError("render.cpp: clearSprite site not found inside render::update")
        line_pos = s.rfind("\n", fn_open, clear_pos) + 1
        block = '''#ifdef SPACECADET_PSP
\t\tif (sprite->DirtyRect.Width > 0 && sprite->DirtyRect.Height > 0)
\t\t\tPspMarkDirtyRect(sprite->DirtyRect.XPosition, sprite->DirtyRect.YPosition,
\t\t\t                 sprite->DirtyRect.Width, sprite->DirtyRect.Height);
#endif
'''
        s = s[:line_pos] + block + s[line_pos:]
        print("[ok]   track PSP dirty sprite rectangles (structural)")
    else:
        print("[skip] track PSP dirty sprite rectangles")

    ball_new_marker = "PspMarkDirtyRect(dirty->XPosition, dirty->YPosition, dirty->Width, dirty->Height);"
    if ball_new_marker not in s:
        fn_pos = s.find("void render::paint_balls()")
        if fn_pos < 0:
            raise RuntimeError("render.cpp: render::paint_balls not found for PSP dirty tracking")
        fn_open = s.find("{", fn_pos)
        fn_close = find_matching_brace(s, fn_open)
        clip_pos = s.find("maths::rectangle_clip(ball->BmpRect, vscreen_rect, &ball->DirtyRect)", fn_open, fn_close)
        if clip_pos < 0:
            raise RuntimeError("render.cpp: ball clip site not found inside render::paint_balls")
        block_open = s.find("{", clip_pos, fn_close)
        if block_open < 0:
            raise RuntimeError("render.cpp: ball clip block not found inside render::paint_balls")
        insert_pos = block_open + 1
        block = '''
#ifdef SPACECADET_PSP
\t\t\tPspMarkDirtyRect(dirty->XPosition, dirty->YPosition, dirty->Width, dirty->Height);
#endif'''
        s = s[:insert_pos] + block + s[insert_pos:]
        print("[ok]   track PSP new ball rectangles (structural)")
    else:
        print("[skip] track PSP new ball rectangles")

    ball_old_marker = "PspMarkDirtyRect(curBall->DirtyRect.XPosition, curBall->DirtyRect.YPosition"
    if ball_old_marker not in s:
        fn_pos = s.find("void render::unpaint_balls()")
        if fn_pos < 0:
            raise RuntimeError("render.cpp: render::unpaint_balls not found for PSP dirty tracking")
        fn_open = s.find("{", fn_pos)
        fn_close = find_matching_brace(s, fn_open)
        if_pos = s.find("if (curBall->DirtyRect.Width > 0)", fn_open, fn_close)
        if if_pos < 0:
            raise RuntimeError("render.cpp: old-ball dirty site not found inside render::unpaint_balls")
        copy_pos = s.find("gdrv::copy_bitmap", if_pos, fn_close)
        if copy_pos < 0:
            raise RuntimeError("render.cpp: old-ball restore copy not found inside render::unpaint_balls")
        semi_pos = s.find(");", copy_pos, fn_close)
        if semi_pos < 0:
            raise RuntimeError("render.cpp: end of old-ball restore copy not found")
        line_if_end = s.find("\n", if_pos, copy_pos)
        if line_if_end < 0:
            raise RuntimeError("render.cpp: malformed old-ball if statement")
        prefix = '''\t\t{
#ifdef SPACECADET_PSP
\t\t\tPspMarkDirtyRect(curBall->DirtyRect.XPosition, curBall->DirtyRect.YPosition,
\t\t\t                 curBall->DirtyRect.Width, curBall->DirtyRect.Height);
#endif
'''
        s = s[:line_if_end + 1] + prefix + s[line_if_end + 1:semi_pos + 2] + "\n\t\t}" + s[semi_pos + 2:]
        print("[ok]   track PSP old ball rectangles (structural)")
    else:
        print("[skip] track PSP old ball rectangles")

    write(p, s)

    print("[ok]   PSP 0.4.3 dirty texture upload + BGR565 presentation")


def patch_vscreen_dirty_tracking(src):
    # Track direct CPU writes to the main vScreen that bypass render sprites.
    render_h = src / "SpaceCadetPinball" / "render.h"
    render_cpp = src / "SpaceCadetPinball" / "render.cpp"
    gdrv_cpp = src / "SpaceCadetPinball" / "gdrv.cpp"

    s = read(render_h)
    decl = "\tstatic void mark_vscreen_dirty(int x, int y, int width, int height);"
    if decl not in s:
        anchor = "\tstatic void PresentVScreen();"
        if anchor not in s:
            raise RuntimeError("render.h: PresentVScreen declaration not found")
        s = s.replace(anchor, anchor + "\n" + decl, 1)
        write(render_h, s)
        print("[ok]   expose PSP vScreen dirty bridge")
    else:
        print("[skip] expose PSP vScreen dirty bridge")

    s = read(render_cpp)
    marker = "PSP_VSCREEN_DIRTY_BRIDGE_041"
    if marker not in s:
        anchor = "void render::update()"
        pos = s.find(anchor)
        if pos < 0:
            raise RuntimeError("render.cpp: render::update not found for vScreen dirty bridge")
        bridge = r'''// PSP_VSCREEN_DIRTY_BRIDGE_041
void render::mark_vscreen_dirty(int x, int y, int width, int height)
{
#ifdef SPACECADET_PSP
	PspMarkDirtyRect(x, y, width, height);
#else
	(void)x; (void)y; (void)width; (void)height;
#endif
}

'''
        s = s[:pos] + bridge + s[pos:]
        write(render_cpp, s)
        print("[ok]   PSP vScreen dirty bridge")
    else:
        print("[skip] PSP vScreen dirty bridge")

    s = read(gdrv_cpp)
    if '#include "render.h"' not in s:
        anchor = '#include "gdrv.h"\n'
        if anchor not in s:
            raise RuntimeError("gdrv.cpp: gdrv.h include not found")
        s = s.replace(anchor, anchor + '#include "render.h"\n', 1)

    def inject_at_function_start(text, signature, code, marker_name):
        if marker_name in text:
            return text, False
        fn = text.find(signature)
        if fn < 0:
            raise RuntimeError(f"gdrv.cpp: function not found: {signature}")
        op = text.find("{", fn)
        if op < 0:
            raise RuntimeError(f"gdrv.cpp: function body not found: {signature}")
        return text[:op + 1] + "\n" + code + text[op + 1:], True

    hooks = [
        (
            "void gdrv::fill_bitmap(gdrv_bitmap8* bmp, int width, int height, int xOff, int yOff, ColorRgba fillColor)",
            r'''#ifdef SPACECADET_PSP
	// PSP_VSCREEN_GDRV_FILL_041
	if (bmp == render::vscreen)
		render::mark_vscreen_dirty(xOff, yOff, width, height);
#endif
''',
            "PSP_VSCREEN_GDRV_FILL_041",
        ),
        (
            "void gdrv::copy_bitmap(gdrv_bitmap8* dstBmp, int width, int height, int xOff, int yOff, gdrv_bitmap8* srcBmp,",
            r'''#ifdef SPACECADET_PSP
	// PSP_VSCREEN_GDRV_COPY_041
	if (dstBmp == render::vscreen)
		render::mark_vscreen_dirty(xOff, yOff, width, height);
#endif
''',
            "PSP_VSCREEN_GDRV_COPY_041",
        ),
        (
            "void gdrv::copy_bitmap_w_transparency(gdrv_bitmap8* dstBmp, int width, int height, int xOff, int yOff,",
            r'''#ifdef SPACECADET_PSP
	// PSP_VSCREEN_GDRV_TRANSPARENT_041
	if (dstBmp == render::vscreen)
		render::mark_vscreen_dirty(xOff, yOff, width, height);
#endif
''',
            "PSP_VSCREEN_GDRV_TRANSPARENT_041",
        ),
        (
            "void gdrv::ScrollBitmapHorizontal(gdrv_bitmap8* bmp, int xStart)",
            r'''#ifdef SPACECADET_PSP
	// PSP_VSCREEN_GDRV_SCROLL_041
	if (bmp == render::vscreen)
		render::mark_vscreen_dirty(0, 0, bmp->Width, bmp->Height);
#endif
''',
            "PSP_VSCREEN_GDRV_SCROLL_041",
        ),
    ]

    changed = False
    for signature, code, marker_name in hooks:
        s, did = inject_at_function_start(s, signature, code, marker_name)
        changed = changed or did
    if changed or '#include "render.h"' in s:
        write(gdrv_cpp, s)
    print("[ok]   track direct gdrv writes to PSP vScreen")


def patch_video_modes(src, upload_mode):
    # PSP: logical/high-res and native-size presentation coexist in one
    # EBOOT and are selected at runtime through Options.Resolution:
    # 0=QUALITY 30 logical, 1=QUALITY 60 logical.
    p = src / "SpaceCadetPinball" / "render.cpp"
    s = read(p)

    # Add native-size texture helpers inside the existing PSP anonymous namespace.
    ns_start = s.find("#ifdef SPACECADET_PSP\nnamespace\n{")
    if ns_start < 0:
        raise RuntimeError("render.cpp: PSP anonymous namespace not found")
    brace = s.find("{", ns_start)
    ns_close = find_matching_brace(s, brace)
    helper = r'''

    // PSP_RUNTIME_VIDEO_050
    SDL_Texture* PspNativeTexture = nullptr;
    int PspNativeWidth = 0;
    int PspNativeHeight = 0;
    int PspLastVideoProfile = -1;
    std::vector<int> PspNativeSampleX;
    std::vector<int> PspNativeSampleY;

    void PspDestroyNativeTexture()
    {
        if (PspNativeTexture) SDL_DestroyTexture(PspNativeTexture);
        PspNativeTexture = nullptr;
        PspNativeWidth = PspNativeHeight = 0;
        PspNativeSampleX.clear();
        PspNativeSampleY.clear();
    }

    bool PspEnsureLogicalTextures(gdrv_bitmap8* screen)
    {
        if (!screen) return false;
        if (PspVScreenLeft && PspScreenHeight == screen->Height &&
            PspLeftWidth + PspRightWidth == screen->Width)
            return true;

        if (PspVScreenLeft) SDL_DestroyTexture(PspVScreenLeft);
        if (PspVScreenRight) SDL_DestroyTexture(PspVScreenRight);
        PspVScreenLeft = PspVScreenRight = nullptr;
        PspLeftWidth = std::min(screen->Width, PspTextureSplitX);
        PspRightWidth = screen->Width - PspLeftWidth;
        PspScreenHeight = screen->Height;
        PspVScreenLeft = PspCreateVScreenTexture(PspLeftWidth, PspScreenHeight);
        if (PspRightWidth > 0)
            PspVScreenRight = PspCreateVScreenTexture(PspRightWidth, PspScreenHeight);
        if (!PspVScreenLeft || (PspRightWidth > 0 && !PspVScreenRight))
            return false;
        PspFullUploadPending = true;
        return true;
    }

    bool PspEnsureNativeTexture(gdrv_bitmap8* screen, int width, int height)
    {
        if (!screen || width <= 0 || height <= 0 || width > 512 || height > 512)
            return false;
        if (PspNativeTexture && PspNativeWidth == width && PspNativeHeight == height)
            return true;

        PspDestroyNativeTexture();
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
        PspNativeTexture = SDL_CreateTexture(winmain::Renderer, SDL_PIXELFORMAT_BGR565,
            SDL_TEXTUREACCESS_STREAMING, width, height);
        if (!PspNativeTexture) return false;
        SDL_SetTextureBlendMode(PspNativeTexture, SDL_BLENDMODE_NONE);
        PspNativeWidth = width;
        PspNativeHeight = height;
        PspNativeSampleX.resize(width);
        PspNativeSampleY.resize(height);
        for (int dx = 0; dx < width; ++dx)
            PspNativeSampleX[dx] = std::min(screen->Width - 1,
                ((2 * dx + 1) * screen->Width) / (2 * width));
        for (int dy = 0; dy < height; ++dy)
            PspNativeSampleY[dy] = std::min(screen->Height - 1,
                ((2 * dy + 1) * screen->Height) / (2 * height));
        PspFullUploadPending = true;
        return true;
    }

    SDL_Rect PspMapDirtyToNative(const SDL_Rect& rect, int logicalW, int logicalH)
    {
        const int x0 = std::max(0, (rect.x * PspNativeWidth) / logicalW - 1);
        const int y0 = std::max(0, (rect.y * PspNativeHeight) / logicalH - 1);
        const int x1 = std::min(PspNativeWidth,
            ((rect.x + rect.w) * PspNativeWidth + logicalW - 1) / logicalW + 1);
        const int y1 = std::min(PspNativeHeight,
            ((rect.y + rect.h) * PspNativeHeight + logicalH - 1) / logicalH + 1);
        return SDL_Rect{x0, y0, std::max(0, x1 - x0), std::max(0, y1 - y0)};
    }

    bool PspUploadNativeRect(gdrv_bitmap8* screen, const SDL_Rect& logicalDirty)
    {
        const SDL_Rect dstRect = PspMapDirtyToNative(logicalDirty, screen->Width, screen->Height);
        if (dstRect.w <= 0 || dstRect.h <= 0) return true;
        PspUploadBuffer565.resize(static_cast<size_t>(dstRect.w) * dstRect.h);
        for (int row = 0; row < dstRect.h; ++row)
        {
            const int sy = PspNativeSampleY[dstRect.y + row];
            auto* dst = PspUploadBuffer565.data() + static_cast<size_t>(row) * dstRect.w;
            for (int col = 0; col < dstRect.w; ++col)
            {
                const int sx = PspNativeSampleX[dstRect.x + col];
                dst[col] = PspPackBgr565(screen->BmpBufPtr1[sy * screen->Stride + sx]);
            }
        }
        return SDL_UpdateTexture(PspNativeTexture, &dstRect, PspUploadBuffer565.data(),
            dstRect.w * static_cast<int>(sizeof(uint16_t))) == 0;
    }

    bool PspUploadNativeVScreen(gdrv_bitmap8* screen, int width, int height)
    {
        if (!PspEnsureNativeTexture(screen, width, height)) return false;
        SDL_Rect full{0, 0, screen->Width, screen->Height};
        int mappedArea = 0;
        for (const auto& r : PspDirtyRects)
        {
            const auto m = PspMapDirtyToNative(r, screen->Width, screen->Height);
            mappedArea += m.w * m.h;
        }
        const bool fullUpload = PspFullUploadPending ||
            mappedArea >= (PspNativeWidth * PspNativeHeight * 3) / 5;
        if (fullUpload)
        {
            if (!PspUploadNativeRect(screen, full)) return false;
        }
        else
        {
            for (const auto& r : PspDirtyRects)
                if (!PspUploadNativeRect(screen, r)) return false;
        }
        PspDirtyRects.clear();
        PspFullUploadPending = false;
        return true;
    }
'''
    s = s[:ns_close] + helper + s[ns_close:]

    # Recreate becomes lazy; the active profile allocates only its own backing.
    fn = s.find("void render::recreate_screen_texture()")
    if fn < 0: raise RuntimeError("render.cpp: recreate_screen_texture not found")
    op = s.find("{", fn); cl = find_matching_brace(s, op)
    new_recreate = r'''void render::recreate_screen_texture()
{
#ifdef SPACECADET_PSP
    PspDestroyVScreenTextures();
    PspDestroyNativeTexture();
    PspLeftWidth = std::min(vscreen->Width, PspTextureSplitX);
    PspRightWidth = vscreen->Width - PspLeftWidth;
    PspScreenHeight = vscreen->Height;
    PspDirtyRects.clear();
    PspFullUploadPending = true;
    PspLastVideoProfile = -1;
#else
    vscreen->CreateTexture(options::Options.LinearFiltering ? "linear" : "nearest", SDL_TEXTUREACCESS_STREAMING);
#endif
}'''
    s = s[:fn] + new_recreate + s[cl+1:]

    # Destroy both possible presentation backings on shutdown.
    old = '''#ifdef SPACECADET_PSP\n\tPspDestroyVScreenTextures();\n#endif'''
    new = '''#ifdef SPACECADET_PSP\n\tPspDestroyVScreenTextures();\n\tPspDestroyNativeTexture();\n#endif'''
    if old not in s: raise RuntimeError("render.cpp: uninit PSP destroy block not found")
    s = s.replace(old, new, 1)

    fn = s.find("void render::PresentVScreen()")
    if fn < 0: raise RuntimeError("render.cpp: PresentVScreen not found")
    op = s.find("{", fn); cl = find_matching_brace(s, op)
    ps = s.find("#ifdef SPACECADET_PSP", op, cl)
    pe = s.find("#else", ps, cl)
    if ps < 0 or pe < 0: raise RuntimeError("render.cpp: PSP PresentVScreen branch not found")
    present = r'''#ifdef SPACECADET_PSP
    // PSP_RUNTIME_VIDEO_050
    const int profile = std::max(0, std::min(1, static_cast<int>(options::Options.Resolution)));
    const bool native = false; // 0.5.1: PERFORMANCE/native profile removed
    if (profile != PspLastVideoProfile)
    {
        // Free the old profile backing so logical + native textures never occupy
        // VRAM at the same time. Force one full refresh after the switch.
        if (native)
        {
            if (PspVScreenLeft) SDL_DestroyTexture(PspVScreenLeft);
            if (PspVScreenRight) SDL_DestroyTexture(PspVScreenRight);
            PspVScreenLeft = PspVScreenRight = nullptr;
        }
        else
        {
            PspDestroyNativeTexture();
        }
        PspDirtyRects.clear();
        PspFullUploadPending = true;
        PspLastVideoProfile = profile;
    }

    if (native)
    {
        if (!PspUploadNativeVScreen(vscreen, DestinationRect.w, DestinationRect.h))
        {
            printf("PSP: native presentation upload failed: %s\\n", SDL_GetError());
            return;
        }
        if (offset_x == 0 && offset_y == 0)
        {
            SDL_RenderCopy(winmain::Renderer, PspNativeTexture, nullptr, &DestinationRect);
        }
        else
        {
            const auto coef = static_cast<float>(pb::MainTable->Width) / vscreen->Width;
            const int splitX = static_cast<int>(std::round(PspNativeWidth * coef));
            auto offX = static_cast<int>(std::round(offset_x * fullscrn::ScaleX));
            auto offY = static_cast<int>(std::round(offset_y * fullscrn::ScaleY));
            if (offset_x && offX == 0) offX = offset_x > 0 ? 1 : -1;
            if (offset_y && offY == 0) offY = offset_y > 0 ? 1 : -1;
            SDL_Rect boardSrc{0, 0, splitX, PspNativeHeight};
            SDL_Rect sideSrc{splitX, 0, PspNativeWidth - splitX, PspNativeHeight};
            SDL_Rect boardDst{DestinationRect.x + offX, DestinationRect.y + offY, splitX, DestinationRect.h};
            SDL_Rect sideDst{DestinationRect.x + splitX, DestinationRect.y, PspNativeWidth - splitX, DestinationRect.h};
            SDL_RenderCopy(winmain::Renderer, PspNativeTexture, &boardSrc, &boardDst);
            SDL_RenderCopy(winmain::Renderer, PspNativeTexture, &sideSrc, &sideDst);
        }
    }
    else
    {
        if (!PspEnsureLogicalTextures(vscreen) || !PspUploadVScreen(vscreen))
        {
            printf("PSP: logical presentation upload failed: %s\\n", SDL_GetError());
            return;
        }
        if (offset_x == 0 && offset_y == 0)
        {
            PspRenderLogicalRange(0, vscreen->Width, DestinationRect);
        }
        else
        {
            const auto coef = static_cast<float>(pb::MainTable->Width) / vscreen->Width;
            const auto srcSplit = static_cast<int>(std::round(vscreen->Width * coef));
            const auto dstSplit = static_cast<int>(std::round(DestinationRect.w * coef));
            auto offX = static_cast<int>(std::round(offset_x * fullscrn::ScaleX));
            auto offY = static_cast<int>(std::round(offset_y * fullscrn::ScaleY));
            if (offset_x && offX == 0) offX = offset_x > 0 ? 1 : -1;
            if (offset_y && offY == 0) offY = offset_y > 0 ? 1 : -1;
            SDL_Rect boardDst{DestinationRect.x + offX, DestinationRect.y + offY, dstSplit, DestinationRect.h};
            SDL_Rect sideDst{DestinationRect.x + dstSplit, DestinationRect.y, DestinationRect.w - dstSplit, DestinationRect.h};
            PspRenderLogicalRange(0, srcSplit, boardDst);
            PspRenderLogicalRange(srcSplit, vscreen->Width - srcSplit, sideDst);
        }
    }
    if (options::Options.DebugOverlay) DebugOverlay::DrawOverlay();
#else'''
    s = s[:ps] + present + s[pe+len("#else"):]
    write(p, s)
    print("[ok]   PSP runtime VIDEO profiles (30 FPS / 60 FPS)")


