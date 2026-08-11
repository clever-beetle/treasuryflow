import pytest
from playwright.sync_api import Page, expect

@pytest.fixture(scope="session")
def app_url():
    # Assume the app is running locally for the test
    return "http://localhost:5000"

def test_desktop_login_success(page: Page, app_url: str):
    """Test successful login on a standard desktop browser."""
    page.goto(f"{app_url}/login")
    
    # Check that we are on the login page
    expect(page).to_have_title("Welcome Back - Treasury Flow")
    
    # Fill in the form
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "password123")
    
    # Submit the form
    page.click("button[type='submit']")
    
    # Wait for navigation to dashboard
    page.wait_for_url(f"{app_url}/")
    expect(page.locator("text=Dashboard")).to_be_visible()

def test_mobile_csrf_login_flow(playwright, app_url: str):
    """
    Simulate a mobile browser (iPhone) to ensure CSRF cookies are set correctly.
    This specifically tests the 'CSRF session token missing' bug resolution.
    """
    # Use iPhone 13 device profile from playwright
    iphone_13 = playwright.devices['iPhone 13']
    
    browser = playwright.webkit.launch()
    context = browser.new_context(**iphone_13)
    page = context.new_page()
    
    page.goto(f"{app_url}/login")
    
    # Check that we are on the login page
    expect(page).to_have_title("Welcome Back - Treasury Flow")
    
    # Verify the hidden csrf_token input exists
    csrf_input = page.locator("input[name='csrf_token']")
    expect(csrf_input).to_be_attached()
    
    # Verify the session cookie was set properly by checking context cookies
    cookies = context.cookies()
    session_cookie = next((c for c in cookies if c['name'] == 'session'), None)
    
    assert session_cookie is not None, "Session cookie was not set on mobile GET request!"
    assert session_cookie['secure'] is True, "Session cookie MUST be marked secure!"
    
    # Fill form
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "password123")
    
    # Submit
    page.click("button[type='submit']")
    
    # If CSRF failed, we'd see 'The CSRF session token is missing'
    # We expect to reach the dashboard instead
    page.wait_for_url(f"{app_url}/")
    expect(page.locator("text=Dashboard")).to_be_visible()
    
    context.close()
    browser.close()
