import pytest
from playwright.sync_api import Page, expect
import os

@pytest.fixture(scope="session")
def app_url():
    # Assume the app is running locally for the test
    return "http://localhost:5000"

def test_login_page_visual_regression(page: Page, app_url: str):
    """
    Test the visual appearance of the login page across devices.
    Requires pytest-playwright-visual plugin if doing exact pixel matching,
    or we can just use native Playwright visual comparisons.
    """
    page.goto(f"{app_url}/login")
    
    # Wait for any animations to finish (Tailwind fade-in)
    page.wait_for_timeout(1000)
    
    # Assert screenshot matches baseline
    # Playwright's expect(page).to_have_screenshot() will compare against snapshots 
    # stored in the repository. If it differs, it will fail the test.
    expect(page).to_have_screenshot("login-page-desktop.png", max_diff_pixels=100)

def test_dashboard_visual_regression_mobile(playwright, app_url: str):
    """
    Test the visual appearance of the dashboard on mobile.
    """
    pixel_5 = playwright.devices['Pixel 5']
    browser = playwright.chromium.launch()
    context = browser.new_context(**pixel_5)
    page = context.new_page()
    
    # We must login first
    page.goto(f"{app_url}/login")
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")
    page.wait_for_url(f"{app_url}/")
    
    # Wait for animations/charts to load
    page.wait_for_timeout(2000)
    
    # Take visual snapshot of mobile dashboard
    expect(page).to_have_screenshot("dashboard-mobile.png", full_page=True, max_diff_pixels=200)
    
    context.close()
    browser.close()
