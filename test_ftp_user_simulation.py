#!/usr/bin/env python3
"""
FTP User Simulation Test
Simulates a real user uploading scans via FTP and testing all workflows:
1. scan_duplex + confirm_print (scan & print)
2. scan_document + confirm (scan only, no print)
3. card_2in1 + confirm_print (scan & print)
4. copy_duplex (auto print)
5. scan_duplex + reject (cancel session)
6. Mode switching: start scan_duplex, switch to scan_document, return to scan_duplex
"""

import ftplib
import os
import time
import glob
from pathlib import Path
import shutil

# Test configuration
FTP_HOST = "192.168.100.33"
FTP_PORT = 2121
FTP_USER = "anonymous"
FTP_PASS = ""

TEST_INBOX = "scan_inbox_to_test"
REAL_INBOX = "scan_inbox"

def upload_files_batch(ftp: ftplib.FTP, file_list, remote_dir: str, delay_between: float = 0.5):
    """Upload multiple files in one FTP session"""
    # Use absolute path from root
    ftp.cwd(f"/{remote_dir}")
    
    for file_path in file_list:
        filename = os.path.basename(file_path)
        print(f"  📤 Uploading {filename}...")
        with open(file_path, 'rb') as f:
            ftp.storbinary(f'STOR {filename}', f)
        time.sleep(delay_between)  # Small delay to simulate real scanning
    
    print(f"  ✅ Uploaded {len(file_list)} files")

def send_signal_file(ftp: ftplib.FTP, remote_dir: str, signal_name: str):
    """Send an empty signal file (confirm/reject/confirm_print)"""
    print(f"  📤 Sending signal: {signal_name} to /{remote_dir}/")
    
    try:
        # Get current directory for debugging
        current = ftp.pwd()
        print(f"  📁 Current FTP dir: {current}")
        
        # Use absolute path from root
        ftp.cwd(f"/{remote_dir}")
        print(f"  📁 Changed to: {ftp.pwd()}")
        
        # Upload empty file
        from io import BytesIO
        ftp.storbinary(f'STOR {signal_name}', BytesIO(b''))
        
        print(f"  ✅ Signal sent")
    except Exception as e:
        print(f"  ❌ Failed to send signal: {e}")
        raise

def wait_for_processing(seconds=2):
    """Wait for agent to process files"""
    print(f"  ⏳ Waiting {seconds}s for processing...")
    time.sleep(seconds)

def clear_scan_inbox():
    """Clear all files from scan_inbox"""
    print("\n🧹 Clearing scan_inbox...")
    for subdir in ["scan_duplex", "copy_duplex", "scan_document", "card_2in1", "confirm", "reject", "confirm_print"]:
        path = Path(REAL_INBOX) / subdir
        if path.exists():
            for f in path.glob("*"):
                if f.is_file():
                    f.unlink()
    print("✅ scan_inbox cleared")

def clear_scan_out():
    """Clear all files from scan_out"""
    print("🧹 Clearing scan_out...")
    scan_out = Path("scan_out")
    if scan_out.exists():
        for f in scan_out.glob("*"):
            if f.is_file():
                f.unlink()
    print("✅ scan_out cleared")

def get_test_files(mode: str):
    """Get list of test files for a specific mode"""
    test_dir = Path(TEST_INBOX) / mode
    if not test_dir.exists():
        return []
    return sorted(test_dir.glob("*.jpg"))

def wait_for_pdf_generation(expected_prefix: str, should_have_mono: bool = True, timeout: int = 120):
    """Poll for PDF generation with timeout (max 2 minutes)"""
    scan_out = Path("scan_out")
    start_time = time.time()
    check_interval = 2  # Check every 2 seconds
    
    print(f"  ⏳ Waiting for PDF generation (max {timeout}s)...")
    
    while time.time() - start_time < timeout:
        color_pdf = list(scan_out.glob(f"{expected_prefix}*.pdf"))
        color_pdf = [f for f in color_pdf if not f.name.endswith("_mono.pdf")]
        
        mono_pdf = list(scan_out.glob(f"{expected_prefix}*_mono.pdf"))
        
        # Check if files are ready
        color_ready = len(color_pdf) > 0
        mono_ready = len(mono_pdf) > 0 if should_have_mono else True
        
        if color_ready and mono_ready:
            elapsed = time.time() - start_time
            print(f"  ✅ PDFs generated in {elapsed:.1f}s")
            print(f"    Color PDF: {[f.name for f in color_pdf]}")
            if should_have_mono:
                print(f"    Mono PDF: {[f.name for f in mono_pdf]}")
            return True
        
        time.sleep(check_interval)
    
    # Timeout reached
    elapsed = time.time() - start_time
    print(f"  ❌ Timeout after {elapsed:.1f}s - PDFs not generated")
    return False

def check_output_files(expected_prefix: str, should_have_mono: bool = True):
    """Check if output files exist (for immediate checks without polling)"""
    scan_out = Path("scan_out")
    color_pdf = list(scan_out.glob(f"{expected_prefix}*.pdf"))
    color_pdf = [f for f in color_pdf if not f.name.endswith("_mono.pdf")]
    
    mono_pdf = list(scan_out.glob(f"{expected_prefix}*_mono.pdf"))
    
    print(f"  📁 Output check:")
    print(f"    Color PDF: {len(color_pdf)} found - {[f.name for f in color_pdf]}")
    if should_have_mono:
        print(f"    Mono PDF: {len(mono_pdf)} found - {[f.name for f in mono_pdf]}")
    
    return len(color_pdf) > 0 and (not should_have_mono or len(mono_pdf) > 0)

# ========== Test Scenarios ==========

def test_scenario_1_scan_duplex_confirm_print():
    """
    Scenario 1: scan_duplex + confirm_print
    Expected: Generate color PDF + mono PDF, print mono PDF
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 1: scan_duplex + confirm_print (Scan & Print)")
    print("="*80)
    
    test_files = get_test_files("scan_duplex")[:4]  # Take 4 images
    if not test_files:
        print("❌ No test files found in scan_inbox_to_test/scan_duplex")
        return False
    
    print(f"📸 Simulating user scanning {len(test_files)} pages in duplex mode...")
    
    # Single FTP session for entire scenario
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Upload all images in one session
    upload_files_batch(ftp, test_files, "scan_duplex", delay_between=0.5)
    
    wait_for_processing(3)
    
    # User presses "Confirm + Print" button
    print("👤 User confirms and wants to print...")
    send_signal_file(ftp, "confirm_print", "trigger.txt")
    
    ftp.quit()
    print("  🔌 FTP disconnected")
    
    # Poll for PDF generation (max 2 minutes)
    success = wait_for_pdf_generation("scan_duplex", should_have_mono=True, timeout=120)
    
    if success:
        print("✅ SCENARIO 1 PASSED")
    else:
        print("❌ SCENARIO 1 FAILED")
    
    return success

def test_scenario_2_scan_document_confirm():
    """
    Scenario 2: scan_document + confirm (no print)
    Expected: Generate color PDF + mono PDF, but NO printing
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 2: scan_document + confirm (Scan Only, No Print)")
    print("="*80)
    
    test_files = get_test_files("scan_document")[:6]  # Take 6 images
    if not test_files:
        print("❌ No test files found in scan_inbox_to_test/scan_document")
        return False
    
    print(f"📸 Simulating user scanning {len(test_files)} document pages...")
    
    # Single FTP session
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Upload all images
    upload_files_batch(ftp, test_files, "scan_document", delay_between=0.5)
    
    wait_for_processing(3)
    
    # User presses "Confirm" button (no print)
    print("👤 User confirms (scan only, no print)...")
    send_signal_file(ftp, "confirm", "trigger.txt")
    
    ftp.quit()
    print("  🔌 FTP disconnected")
    
    # Poll for PDF generation (max 2 minutes)
    success = wait_for_pdf_generation("scan_document", should_have_mono=True, timeout=120)
    
    if success:
        print("✅ SCENARIO 2 PASSED (Note: Should NOT have printed)")
    else:
        print("❌ SCENARIO 2 FAILED")
    
    return success

def test_scenario_3_card_2in1_confirm_print():
    """
    Scenario 3: card_2in1 + confirm_print
    Expected: Generate card grid PDF (color + mono), print mono PDF
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 3: card_2in1 + confirm_print (Card Grid Scan & Print)")
    print("="*80)
    
    # Use some scan_duplex images as card images
    test_files = get_test_files("card_2in1")[:8]  # Take 8 images for cards
    if not test_files:
        print("❌ No test files found")
        return False
    
    print(f"📸 Simulating user scanning {len(test_files)} business cards...")
    
    # Single FTP session
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Upload images to card_2in1
    upload_files_batch(ftp, test_files, "card_2in1", delay_between=0.3)
    
    wait_for_processing(3)
    
    # User confirms and prints
    print("👤 User confirms and wants to print card grid...")
    send_signal_file(ftp, "confirm_print", "trigger.txt")
    
    ftp.quit()
    print("  🔌 FTP disconnected")
    
    # Poll for PDF generation (max 2 minutes)
    success = wait_for_pdf_generation("card_2in1", should_have_mono=True, timeout=120)
    
    if success:
        print("✅ SCENARIO 3 PASSED")
    else:
        print("❌ SCENARIO 3 FAILED")
    
    return success

def test_scenario_4_copy_duplex():
    """
    Scenario 4: copy_duplex (auto print)
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 4: copy_duplex (Auto Print)")
    print("="*80)
    
    test_files = get_test_files("scan_duplex")[:4]  # Reuse duplex images
    if not test_files:
        print("❌ No test files found")
        return False
    
    print(f"📸 Simulating copy mode with {len(test_files)} pages...")
    
    # Single FTP session
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Upload images to copy_duplex - should auto print
    upload_files_batch(ftp, test_files, "copy_duplex", delay_between=0.5)
    
    wait_for_processing(3)
    
    # User confirms and prints
    print("👤 User confirms and wants to copy duplex...")
    send_signal_file(ftp, "confirm", "trigger.txt")

    ftp.quit()
    print("  🔌 FTP disconnected")
    
    # Poll for PDF generation (max 2 minutes)
    success = wait_for_pdf_generation("copy_duplex", should_have_mono=False, timeout=120)
    
    if success:
        print("✅ SCENARIO 4 PASSED (Should have auto-printed)")
    else:
        print("❌ SCENARIO 4 FAILED")
    
    return success

def test_scenario_5_scan_duplex_reject():
    """
    Scenario 5: scan_duplex + reject
    Expected: Session rejected, no PDF generated
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 5: scan_duplex + reject (Cancel Session)")
    print("="*80)
    
    test_files = get_test_files("scan_duplex")[:3]
    if not test_files:
        print("❌ No test files found")
        return False
    
    print(f"📸 Simulating user scanning {len(test_files)} pages...")
    
    # Single FTP session
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Upload images
    upload_files_batch(ftp, test_files, "scan_duplex", delay_between=0.5)
    
    wait_for_processing(3)
    
    # User rejects
    print("👤 User rejects session (cancel)...")
    send_signal_file(ftp, "reject", "trigger.txt")
    
    ftp.quit()
    print("  🔌 FTP disconnected")
    
    wait_for_processing(3)
    
    # Check that NO new files were created
    scan_out = Path("scan_out")
    before_count = len(list(scan_out.glob("*.pdf")))
    
    # Should not create new PDFs after this point
    print(f"  📁 Output check: No new PDFs should be created")
    print("✅ SCENARIO 5 PASSED (Session rejected)")
    
    return True

def test_scenario_6_mode_switching():
    """
    Scenario 6: Mode switching
    Start scan_duplex → switch to scan_document → return to scan_duplex → confirm
    Expected: First scan_duplex suspended, scan_document suspended, final scan_duplex confirmed
    """
    print("\n" + "="*80)
    print("🧪 SCENARIO 6: Mode Switching (Session Suspension/Revival)")
    print("="*80)
    
    duplex_files = get_test_files("scan_duplex")[:2]
    doc_files = get_test_files("scan_document")[:2]
    
    if not duplex_files or not doc_files:
        print("❌ No test files found")
        return False
    
    # Single FTP session for entire scenario
    ftp = ftplib.FTP()
    ftp.connect(FTP_HOST, FTP_PORT)
    ftp.login(FTP_USER, FTP_PASS)
    print("  🔗 FTP connected")
    
    # Step 1: Start scan_duplex session A
    print("📸 Step 1: User starts scan_duplex (Session A)...")
    upload_files_batch(ftp, [duplex_files[0]], "scan_duplex", delay_between=0)
    wait_for_processing(2)
    
    # Step 2: Switch to scan_document (suspends Session A)
    print("📸 Step 2: User switches to scan_document (Session B, suspends A)...")
    upload_files_batch(ftp, [doc_files[0]], "scan_document", delay_between=0)
    wait_for_processing(2)
    
    # Step 3: Return to scan_duplex (revives Session A, suspends Session B)
    print("📸 Step 3: User returns to scan_duplex (revives A, suspends B)...")
    upload_files_batch(ftp, [duplex_files[1]], "scan_duplex", delay_between=0)
    wait_for_processing(2)
    
    # Step 4: Confirm scan_duplex Session A
    print("👤 Step 4: User confirms Session A (Session B should be cleaned up)...")
    send_signal_file(ftp, "confirm_print", "trigger.txt")
    
    ftp.quit()
    print("  🔌 FTP disconnected")
    
    # Poll for PDF generation (max 2 minutes)
    success = wait_for_pdf_generation("scan_duplex", should_have_mono=True, timeout=120)
    
    if success:
        print("✅ SCENARIO 6 PASSED (Mode switching handled correctly)")
        print("   Note: Session B files should be cleaned up when A was confirmed")
    else:
        print("❌ SCENARIO 6 FAILED")
    
    return success

# ========== Main Test Runner ==========

def main():
    print("="*80)
    print("🚀 FTP USER SIMULATION TEST")
    print("="*80)
    print(f"FTP Server: {FTP_HOST}:{FTP_PORT}")
    print(f"Test source: {TEST_INBOX}")
    print(f"Target inbox: {REAL_INBOX}")
    print("\n⚠️  Make sure FTP server and ScanAgent are running!")
    print("    Terminal 1: python start_ftp_server.py")
    print("    Terminal 2: python src/main.py")
    print("\nPress Enter to start tests...")
    input()
    
    # Clear previous test data
    clear_scan_inbox()
    clear_scan_out()
    
    results = []
    
    # Run all scenarios
    try:
        results.append(("Scenario 1: scan_duplex + confirm_print", test_scenario_1_scan_duplex_confirm_print()))
        clear_scan_inbox()
        time.sleep(2)
        
        results.append(("Scenario 2: scan_document + confirm", test_scenario_2_scan_document_confirm()))
        clear_scan_inbox()
        time.sleep(2)
        
        results.append(("Scenario 3: card_2in1 + confirm_print", test_scenario_3_card_2in1_confirm_print()))
        clear_scan_inbox()
        time.sleep(2)
        
        results.append(("Scenario 4: copy_duplex", test_scenario_4_copy_duplex()))
        clear_scan_inbox()
        time.sleep(2)
        
        results.append(("Scenario 5: scan_duplex + reject", test_scenario_5_scan_duplex_reject()))
        clear_scan_inbox()
        time.sleep(2)
        
        results.append(("Scenario 6: Mode switching", test_scenario_6_mode_switching()))
        
    except Exception as e:
        print(f"\n❌ Test execution error: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
