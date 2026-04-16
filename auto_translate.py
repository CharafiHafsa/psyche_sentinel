import polib
from deep_translator import GoogleTranslator
import os

# The path to your French dictionary
PO_FILE_PATH = os.path.join('locale', 'fr', 'LC_MESSAGES', 'django.po')

def run_translation():
    if not os.path.exists(PO_FILE_PATH):
        print(f"Error: Could not find {PO_FILE_PATH}. Did you run makemessages first?")
        return

    print("Loading French dictionary...")
    po = polib.pofile(PO_FILE_PATH)
    translator = GoogleTranslator(source='en', target='fr')

    # Find all entries that haven't been translated yet
    untranslated = po.untranslated_entries()
    
    if not untranslated:
        print("Everything is already translated!")
        return

    print(f"Found {len(untranslated)} untranslated phrases. Contacting translation server...")
    
    translated_count = 0
    for entry in untranslated:
        try:
            # Skip empty strings
            if not entry.msgid.strip():
                continue
                
            translation = translator.translate(entry.msgid)
            entry.msgstr = translation
            translated_count += 1
            print(f"✓ Translated: '{entry.msgid}' -> '{entry.msgstr}'")
        except Exception as e:
            print(f"✗ Error translating '{entry.msgid}': {e}")

    # Save the file back to the disk
    po.save()
    print(f"\nDone! Successfully auto-translated {translated_count} new entries.")

if __name__ == "__main__":
    run_translation()
    