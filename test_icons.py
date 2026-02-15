"""Quick test for icon rendering."""
import sys
from PySide6.QtWidgets import QApplication
from keyvox.ui.icons import render_icon


def test_icons():
    """Test all icon states."""
    app = QApplication(sys.argv)

    states = ["idle", "recording", "processing", "success", "error"]

    for state in states:
        try:
            icon = render_icon(state, phase=0)
            print(f"[OK] {state:12} - rendered successfully")
        except Exception as e:
            print(f"[ERR] {state:12} - ERROR: {e}")
            return False

    # Test animation phases
    try:
        render_icon("recording", phase=50)
        render_icon("processing", phase=180)
        print(f"[OK] {'animations':12} - phase rendering works")
    except Exception as e:
        print(f"[ERR] {'animations':12} - ERROR: {e}")
        return False

    print("\n[OK] All icon rendering tests passed")
    return True


if __name__ == "__main__":
    success = test_icons()
    sys.exit(0 if success else 1)
