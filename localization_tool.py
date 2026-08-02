#!/usr/bin/env python3
"""
Munchkin Digital — Localization Tool (TUI)

Export text from individual language sections embedded in the game's
UnityFS localization binary, and import edited text back.

The binary stores 15 languages sequentially, each prefixed with a
small binary header identifying the locale code (ko_KR, fr_FR, etc.).

Usage:
    python localization_tool.py

Options (headless):
    python localization_tool.py --export <lang> [-o out.txt]
    python localization_tool.py --import <lang> -i in.txt
    python localization_tool.py --list
    python localization_tool.py --make-installer
"""

import os, sys, struct, shutil, json, zipfile
from pathlib import Path

TEXT_MARKER = b'#_=_'

# ── Binary parsing ──────────────────────────────────────────────────

def read_cstring(data, offset):
    """Read a null-terminated string."""
    end = data.find(b'\x00', offset)
    if end < 0:
        return data[offset:].decode('utf-8'), len(data)
    return data[offset:end].decode('utf-8'), end + 1


def find_languages(data):
    """
    Scan the binary for all language sections.
    Returns [(lang_code, text_start, text_end, section_end), ...]
    text_start   = position of #_=_
    text_end     = position after last text line (before binary metadata)
    section_end  = position of next section's binary header (or EOF)
    """
    # Find all #_=_ marker positions
    marker_positions = []
    pos = 0
    while True:
        idx = data.find(TEXT_MARKER, pos)
        if idx < 0:
            break
        marker_positions.append(idx)
        pos = idx + 1

    if not marker_positions:
        return []

    lang_order = ['ko_KR', 'cs_CZ', 'de_DE', 'zh_TW', 'pt_PT',
                  'it_IT', 'ja_JP', 'fr_FR', 'tr_TR', 'es_ES',
                  'uk_UA', 'ru_RU', 'pl_PL', 'en_US', 'zh_CN']

    sections = []
    for i, marker_pos in enumerate(marker_positions):
        # Determine section end (next section's \x05\x00\x00\x00 header or EOF)
        if i + 1 < len(marker_positions):
            next_marker = marker_positions[i + 1]
            search_area = data[marker_pos:next_marker]
            hdr_idx = search_area.rfind(b'\x05\x00\x00\x00')
            if hdr_idx >= 0:
                section_end = marker_pos + hdr_idx
            else:
                section_end = next_marker
        else:
            section_end = len(data)
            while section_end > marker_pos and data[section_end - 1] == 0:
                section_end -= 1

        # Find where text ends: last \n before non-UTF8 tail
        section_data = data[marker_pos:section_end]
        last_nl = section_data.rfind(b'\n')
        if last_nl >= 0:
            tail = section_data[last_nl + 1:]
            try:
                tail.decode('utf-8')
                text_end = section_end
            except UnicodeDecodeError:
                text_end = marker_pos + last_nl + 1
        else:
            text_end = section_end

        # Find language code in the 64 bytes before the marker
        search_start = max(0, marker_pos - 64)
        header_area = data[search_start:marker_pos]

        lang_code = None
        for lc in lang_order:
            if lc.encode() in header_area:
                lang_code = lc
                break

        if lang_code:
            sections.append((lang_code, marker_pos, text_end, section_end))

    return sections


def get_text_from_section(data, lang, sections=None):
    """Extract the raw key=value text from a language section."""
    if sections is None:
        sections = find_languages(data)
    for l, start, end, _ in sections:
        if l == lang:
            raw = data[start:end]
            while raw and raw[-1] == 0:
                raw = raw[:-1]
            return raw.decode('utf-8', errors='surrogateescape')
    raise ValueError(f"Language '{lang}' not found")


def set_text_in_section(data, lang, new_text, sections=None):
    """Replace the text in a language section within the binary.
    The new text replaces the exact byte span (text_start, text_end),
    padded or trimmed with nulls to maintain all file offsets."""
    if sections is None:
        sections = find_languages(data)

    for l, start, text_end, section_end in sections:
        if l == lang:
            section_size = text_end - start
            encoded = new_text.replace('\r\n', '\n').encode('utf-8', errors='surrogateescape')
            if not encoded.endswith(b'\x00'):
                encoded += b'\x00'
            if len(encoded) < section_size:
                encoded += b'\x00' * (section_size - len(encoded))
            elif len(encoded) > section_size:
                encoded = encoded[:section_size]
            return data[:start] + encoded + data[text_end:]

    raise ValueError(f"Language '{lang}' not found")


def validate_text(text):
    """Return list of validation errors."""
    lines = text.replace('\r\n', '\n').split('\n')
    errors = []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if '=' not in s:
            errors.append(f"L{i}: missing '=' — {s[:60]}")
    return errors


# ── File helpers ─────────────────────────────────────────────────────

def get_platform_files(game_path):
    """Return dict of {name: path} for all platform localization files."""
    loc = Path(game_path) / 'Munchkin_Data' / 'StreamingAssets' / 'Localization'
    return {p: str(loc / p / 'localization') for p in ('win', 'osx', 'android', 'ios')}


def detect_game_path():
    """Auto-detect the game root."""
    for c in [Path.cwd(), Path.cwd().parent, Path(__file__).resolve().parent,
              Path(__file__).resolve().parent.parent]:
        if (c / 'Munchkin_Data' / 'StreamingAssets' / 'Localization').is_dir():
            return str(c)
    return str(Path.cwd())


def load_binary(game_path=None, platform='win'):
    """Load a localization binary from the game."""
    if game_path is None:
        game_path = detect_game_path()
    files = get_platform_files(game_path)
    path = files.get(platform)
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"No localization file for {platform}")
    return Path(path).read_bytes()


def update_unity_cache(game_path, data):
    """Update Unity cache for immediate effect."""
    cache = Path.home() / 'AppData' / 'LocalLow' / 'Unity' / 'Dire Wolf Digital_Munchkin' / 'localization'
    if not cache.is_dir():
        return 0
    count = 0
    for d in cache.iterdir():
        if d.is_dir():
            df = d / '__data'
            if df.exists():
                shutil.copy2(df, df.with_suffix('.bak'))
                df.write_bytes(data)
                count += 1
    return count


# ── TUI ──────────────────────────────────────────────────────────────

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def pause():
    input("\n  Press Enter to continue...")


def pick_lang(sections, prompt="Select language", include_all=False):
    """Let user pick a language from available sections."""
    labels = {
        'ko_KR': 'Korean', 'cs_CZ': 'Czech', 'de_DE': 'German',
        'zh_TW': 'Chinese (Taiwan)', 'pt_PT': 'Portuguese (Portugal)',
        'it_IT': 'Italian', 'ja_JP': 'Japanese', 'fr_FR': 'French (→ Hungarian)',
        'tr_TR': 'Turkish', 'es_ES': 'Spanish', 'uk_UA': 'Ukrainian',
        'ru_RU': 'Russian', 'pl_PL': 'Polish', 'en_US': 'English',
        'zh_CN': 'Chinese (Simplified)',
    }
    items = [(l, s, e) for l, s, e, se in sections if l in labels or True]
    print(f"  {prompt}:\n")
    for i, (l, s, e) in enumerate(items, 1):
        size = e - s
        label = labels.get(l, l)
        print(f"    [{i:>2}]  {l:<8} {size:>8,} bytes  — {label}")
    print()
    val = input(f"  Choice (1-{len(items)}, 'b'=back): ").strip()
    if val.lower() == 'b':
        return None
    try:
        idx = int(val) - 1
        if 0 <= idx < len(items):
            return items[idx][0]
    except ValueError:
        pass
    return pick_lang(sections, prompt)


# ── Actions ─────────────────────────────────────────────────────────

def action_export(game_path):
    data = load_binary(game_path)
    sections = find_languages(data)
    
    while True:
        clear()
        print("=" * 60)
        print("  Export: Language Text → .txt File")
        print("=" * 60)
        lang = pick_lang(sections, "Export which language")
        if lang is None:
            return
        
        text = get_text_from_section(data, lang, sections)
        errors = validate_text(text)
        
        if errors:
            print(f"\n  ⚠ {len(errors)} validation issues:")
            for e in errors[:3]:
                print(f"    {e}")
            if len(errors) > 3:
                print(f"    ... and {len(errors)-3} more")
        
        default = f"localization_{lang}.txt"
        out = input(f"\n  Output file [{default}]: ").strip() or default
        Path(out).write_text(text, encoding='utf-8')
        lines = text.count('\n') + 1
        print(f"\n  ✓ {lang}: {len(text):,} bytes ({lines} lines) → {out}")
        pause()


def action_import(game_path):
    data = load_binary(game_path)
    sections = find_languages(data)
    
    while True:
        clear()
        print("=" * 60)
        print("  Import: .txt File → Game Binary")
        print("=" * 60)
        print("\n  WARNING: Modifies game files. Backups created automatically.\n")
        
        txt_in = input("  Path to .txt file (or 'b'=back): ").strip()
        if txt_in.lower() == 'b':
            return
        if not os.path.exists(txt_in):
            print(f"\n  ERROR: file not found")
            pause()
            continue
        
        new_text = Path(txt_in).read_text(encoding='utf-8')
        errors = validate_text(new_text)
        if errors:
            print(f"\n  ⚠ {len(errors)} validation errors:")
            for e in errors[:8]:
                print(f"    {e}")
            if len(errors) > 8:
                print(f"    ... and {len(errors)-8} more")
            if input("  Continue? (y/N): ").strip().lower() != 'y':
                continue
        
        lang = pick_lang(sections, "Import into which language slot")
        if lang is None:
            continue
        
        try:
            new_data = set_text_in_section(data, lang, new_text, sections)
        except ValueError as e:
            print(f"\n  ERROR: {e}")
            pause()
            continue
        
        files = get_platform_files(game_path)
        for pname, ppath in files.items():
            if not os.path.exists(ppath):
                continue
            # Backup
            bak = ppath + '.original'
            if not os.path.exists(bak):
                shutil.copy2(ppath, bak)
            
            if pname == 'win':
                # Already have new_data computed
                Path(ppath).write_bytes(new_data)
            else:
                # Apply to other platforms (same binary structure)
                pdata = Path(ppath).read_bytes()
                psections = find_languages(pdata)
                pnew = set_text_in_section(pdata, lang, new_text, psections)
                Path(ppath).write_bytes(pnew)
            print(f"  ✓ {pname} updated")
        
        print(f"\n  ✓ {lang} updated across all platforms")
        
        if input("  Update Unity cache? (Y/n): ").strip().lower() != 'n':
            n = update_unity_cache(game_path, new_data)
            print(f"  ✓ {n} cache(s) updated")
        
        pause()
        return  # Single import then back to menu


def action_compare(game_path):
    data = load_binary(game_path)
    sections = find_languages(data)
    
    clear()
    print("=" * 60)
    print("  Compare: .txt vs Game Binary")
    print("=" * 60)
    
    txt_in = input("\n  Path to .txt file (or 'b'=back): ").strip()
    if txt_in.lower() == 'b':
        return
    if not os.path.exists(txt_in):
        print(f"\n  ERROR: file not found")
        pause()
        return
    
    txt_lines = Path(txt_in).read_text(encoding='utf-8').replace('\r\n', '\n').split('\n')
    
    lang = pick_lang(sections, "Compare against which language")
    if lang is None:
        return
    
    bin_text = get_text_from_section(data, lang, sections)
    bin_lines = bin_text.replace('\r\n', '\n').split('\n')
    
    diff = list(difflib.unified_diff(bin_lines, txt_lines,
                                      fromfile=f'game ({lang})', tofile=os.path.basename(txt_in),
                                      lineterm=''))
    if not diff:
        print("\n  ✓ Identical")
    else:
        print(f"\n  {len(diff)} diff lines (showing 50):\n")
        for line in diff[:50]:
            if line.startswith('+'):
                print(f"  \033[32m{line}\033[0m")
            elif line.startswith('-'):
                print(f"  \033[31m{line}\033[0m")
            elif line.startswith('@@'):
                print(f"  \033[36m{line}\033[0m")
            else:
                print(f"  {line}")
        if len(diff) > 50:
            print(f"  ... {len(diff)-50} more")
    pause()


def action_info(game_path):
    data = load_binary(game_path)
    sections = find_languages(data)
    
    clear()
    print("=" * 60)
    print("  File Information")
    print("=" * 60)
    print(f"\n  Game: {game_path}\n")
    print(f"  {'Lang':<8} {'Section size':>14} {'Keys':>8}")
    print(f"  {'─'*8} {'─'*14} {'─'*8}")
    
    for l, s, e, se in sections:
        section_data = data[s:e]
        marker = section_data.find(TEXT_MARKER)
        if marker >= 0:
            text_content = section_data[marker:]
            # Trim trailing nulls
            while text_content and text_content[-1] == 0:
                text_content = text_content[:-1]
            try:
                keys = text_content.decode('utf-8').count('=') - 1  # exclude #_=_
            except:
                keys = 0
        else:
            keys = 0
        print(f"  {l:<8} {e-s:>14,} {keys:>8}")
    
    print(f"\n  Total: {len(data):,} bytes across all languages")
    
    hu_txt = Path(game_path) / 'hungarian.txt'
    if hu_txt.exists():
        sz = hu_txt.stat().st_size
        lines = hu_txt.read_text(encoding='utf-8').count('\n') + 1
        print(f"\n  hungarian.txt: {sz:,} bytes, {lines} lines")
    
    pause()


def action_make_installer(game_path):
    """Re-create Munchkin_HU_Installer.zip from current game files."""
    clear()
    print("=" * 60)
    print("  Create Hungarian Installer ZIP")
    print("=" * 60)
    
    # Check for hu_temp/install.bat and hu_temp/data/
    script_dir = Path(__file__).resolve().parent
    bat_path = script_dir / 'hu_temp' / 'install.bat'
    data_dir = script_dir / 'hu_temp' / 'data'
    hu_txt = Path(game_path) / 'hungarian.txt'
    
    if not bat_path.exists() or not data_dir.is_dir():
        print("\n  Build ZIP directly from game files?")
        
        # Use game's win localization binary + hungarian.txt + install.bat from repo
        # but we need install.bat — check if it's somewhere
        install_bat_src = None
        for candidate in [Path(game_path) / 'install.bat', script_dir / 'install.bat']:
            if candidate.exists():
                install_bat_src = candidate
                break
        
        if install_bat_src is None:
            print("\n  ✗ Cannot find install.bat or hu_temp/ folder.")
            print("    Place the installer template at install.bat or hu_temp/install.bat")
            pause()
            return
        
        # Use game binaries directly
        files = get_platform_files(game_path)
        zip_path = Path(game_path) / 'Munchkin_HU_Installer.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(install_bat_src, 'install.bat')
            if hu_txt.exists():
                zf.write(hu_txt, 'hungarian.txt')
            for pname, ppath in files.items():
                if os.path.exists(ppath):
                    zf.write(ppath, f'data/{pname}')
        print(f"\n  ✓ {zip_path} ({zip_path.stat().st_size:,} bytes)")
    else:
        # Use hu_temp template
        zip_path = Path(game_path) / 'Munchkin_HU_Installer.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(bat_path, 'install.bat')
            if hu_txt.exists():
                zf.write(hu_txt, 'hungarian.txt')
            for pname in ('win', 'osx', 'android', 'ios'):
                pf = data_dir / pname
                if pf.exists():
                    zf.write(pf, f'data/{pname}')
        print(f"\n  ✓ {zip_path} ({zip_path.stat().st_size:,} bytes)")
    
    pause()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    game_path = detect_game_path()
    
    # ── Headless mode ──
    if '--list' in sys.argv:
        data = load_binary(game_path)
        sections = find_languages(data)
        for l, s, e, se in sections:
            print(f"{l}  {e-s}")
        return
    
    if '--export' in sys.argv:
        idx = sys.argv.index('--export')
        lang = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'fr_FR'
        out = None
        if '-o' in sys.argv:
            oi = sys.argv.index('-o')
            out = sys.argv[oi + 1] if oi + 1 < len(sys.argv) else None
        if out is None:
            out = f'localization_{lang}.txt'
        data = load_binary(game_path)
        sections = find_languages(data)
        text = get_text_from_section(data, lang, sections)
        Path(out).write_text(text, encoding='utf-8')
        print(f"Exported {lang} → {out} ({len(text):,} bytes)")
        return
    
    if '--import' in sys.argv:
        idx = sys.argv.index('--import')
        lang = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'fr_FR'
        inp = None
        if '-i' in sys.argv:
            ii = sys.argv.index('-i')
            inp = sys.argv[ii + 1] if ii + 1 < len(sys.argv) else None
        if inp is None or not os.path.exists(inp):
            print("ERROR: specify input with -i <file>")
            sys.exit(1)
        new_text = Path(inp).read_text(encoding='utf-8')
        files = get_platform_files(game_path)
        for pname, ppath in files.items():
            if not os.path.exists(ppath):
                continue
            pdata = Path(ppath).read_bytes()
            psections = find_languages(pdata)
            bak = ppath + '.original'
            if not os.path.exists(bak):
                shutil.copy2(ppath, bak)
            Path(ppath).write_bytes(set_text_in_section(pdata, lang, new_text, psections))
            print(f"✓ {pname} updated")
        print(f"Imported {inp} → {lang} on all platforms")
        return
    
    if '--make-installer' in sys.argv:
        action_make_installer(game_path)
        return
    
    # ── Interactive TUI ──
    actions = [
        ('1', 'Export   language section → .txt',     action_export),
        ('2', 'Import   .txt → language section',     action_import),
        ('3', 'Compare  .txt vs language in game',    action_compare),
        ('4', 'Info     language sections overview',  action_info),
        ('5', 'Installer  recreate HU installer ZIP', action_make_installer),
        ('q', 'Quit',                                 None),
    ]
    
    while True:
        clear()
        print("=" * 60)
        print("  Munchkin Digital — Localization Tool")
        print("=" * 60)
        print(f"  Game: {game_path}\n")
        
        print("  Main Menu:\n")
        for key, label, _ in actions:
            print(f"    [{key}]  {label}")
        print()
        
        choice = input("  Choice: ").strip().lower()
        if choice == 'q':
            clear()
            print("Goodbye!")
            break
        
        for key, _, cb in actions:
            if choice == key:
                cb(game_path)
                break


if __name__ == '__main__':
    import difflib
    main()
