import pytest
from playwright.sync_api import Page, expect

def test_homepage_loads(page: Page):
    # This is an E2E visual test script using Playwright
    # It attempts to load the deployed app or local app and verify the UI.
    
    # Normally we'd run this against localhost, but for CI we can run it against the staging URL.
    page.goto("https://www.treasuryflow.web.id/")
    
    # Expect a title "to contain" a substring.
    expect(page).to_have_title("Finance Tracker")
    
    # Assert login form exists
    expect(page.locator("text=Sign In")).to_be_visible()
    
    # Note: A real E2E test would type in username and password, then click login, and assert the dashboard loads.
    # We do not put real passwords in test code, so this serves as a foundation!
