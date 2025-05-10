from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response
from admin.routes import admin
from middleware import init_middleware, require_api_key
from models import stats, user_activity
from config import Config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import os
import time
from io import BytesIO
from PIL import Image
from collections import OrderedDict
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config.from_object(Config)

# Register blueprints
app.register_blueprint(admin)

# Initialize middleware
init_middleware(app)
app.json.ensure_ascii = False            # don’t escape non‑ASCII
app.json.mimetype    = "application/json; charset=utf-8"

@app.template_filter('regex_match')
def regex_match(value, pattern):
    import re
    return bool(re.match(pattern, value))

# Configure Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument('--disable-extensions')
chrome_options.add_argument('--proxy-server="direct://"')
chrome_options.add_argument('--proxy-bypass-list=*')
chrome_options.add_argument('--start-maximized')
chrome_options.add_argument('--disable-setuid-sandbox')
chrome_options.add_argument('--disable-infobars')
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument('--allow-running-insecure-content')
chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
chrome_options.add_experimental_option('useAutomationExtension', False)

# Initialize WebDriver
driver = None

def init_driver():
    global driver
    if driver is None:
        try:
            # First try to find Chrome in the standard Linux path (for Render)
            chrome_path = '/usr/bin/google-chrome'
            service = Service(chrome_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"Failed to initialize with standard Chrome path: {e}")
            try:
                # Fallback to ChromeDriverManager (for local development)
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                print(f"Failed to initialize driver: {e}")
                raise

def get_captcha_screenshot():
    try:
        # Wait for captcha image to be present and visible
        wait = WebDriverWait(driver, 10)
        captcha_element = wait.until(
            EC.presence_of_element_located((By.ID, 'CaptchaImage'))
        )
        wait.until(EC.visibility_of(captcha_element))
        
        # Ensure the element is in view
        driver.execute_script("arguments[0].scrollIntoView(true);", captcha_element)
        
        # Wait a bit for any animations to complete
        time.sleep(0.5)
        
        # Take screenshot of captcha
        captcha_screenshot = captcha_element.screenshot_as_png
        if not captcha_screenshot:
            raise Exception("Screenshot was empty")
            
        return captcha_screenshot
    except Exception as e:
        print(f"Error capturing captcha: {str(e)}")
        return None

def _to_title_case_if_latin(text):
    if not isinstance(text, str):
        return text
    # Only title-case if text contains Latin letters
    if any('a' <= c.lower() <= 'z' for c in text):
        return text.title()
    return text

def _format_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%d %B %Y")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str

# --- Mapping function for ordered JSON output ---
def map_verification_data(raw_data):
    def get(key):
        val = raw_data.get(key, "")
        if key in ["Registration Date", "Issuance Date", "Date of Birth", "birthPlaceEn"]:
            # Try to format as date
            val = _format_date(val)
        return _to_title_case_if_latin(val)
    return OrderedDict([
        ("office", get("Registration Office")),
        ("address", _to_title_case_if_latin(raw_data.get("address", ""))),
        ("register", get("Registration Date")),
        ("issue", get("Issuance Date")),
        ("brn", get("Birth Registration Number")),
        ("dob", get("Date of Birth")),
        ("sex", get("Sex")),
        ("nameEn", get("Registered Person Name")),
        ("nameBn", raw_data.get("নিবন্ধিত ব্যক্তির নাম", "")),
        ("fatherNameEn", get("Father's Name")),
        ("fatherNameBn", raw_data.get("পিতার নাম", "")),
        ("fatherNationalityEn", get("Father's Nationality")),
        ("fatherNationalityBn", raw_data.get("পিতার জাতীয়তা", raw_data.get("পিতার জাতীয়তা", ""))),
        ("motherNameEn", get("Mother's Name")),
        ("motherNameBn", raw_data.get("মাতার নাম", "")),
        ("motherNationalityEn", get("Mother's Nationality")),
        ("motherNationalityBn", raw_data.get("মাতার জাতীয়তা", raw_data.get("মাতার জাতীয়তা", ""))),
        ("birthPlaceEn", get("birthPlaceEn")),
        ("birthPlaceBn", raw_data.get("জন্মস্থান", "")),
    ])

@app.route('/')
def home():
    try:
        # Initialize driver if needed
        init_driver()
        # Refresh the actual website
        driver.get('https://everify.bdris.gov.bd/')
        time.sleep(2)  # Wait for page to load completely
        # Get new captcha immediately
        get_captcha_screenshot()
    except Exception as e:
        print(f"Error refreshing page: {str(e)}")
    return render_template('index.html')

@app.route('/get_captcha')
def get_captcha():
    try:
        # Initialize driver if needed
        init_driver()
        
        # Navigate to the verification page if needed
        if 'everify.bdris.gov.bd' not in driver.current_url:
            driver.execute_script('window.stop();')  # Stop any current loading
            driver.get('https://everify.bdris.gov.bd/')
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, 'ubrn'))
                )
            except Exception as e:
                print(f"Error waiting for page load: {str(e)}")
                driver.refresh()
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, 'ubrn'))
                )
        
        # Wait a short time for the captcha to load
        time.sleep(1)
        
        # Get captcha screenshot
        captcha_image = get_captcha_screenshot()
        if captcha_image:
            return send_file(
                BytesIO(captcha_image),
                mimetype='image/png'
            )
        return jsonify({'error': 'Failed to capture captcha'}), 500
    except Exception as e:
        print(f"Error capturing captcha: {str(e)}")
        return jsonify({'error': 'Failed to capture captcha'}), 500

@app.route('/submit', methods=['POST'])
def submit():
    global driver
    try:
        data = request.json
        reg_number = data.get('regNumber')
        dob = data.get('dob')
        captcha = data.get('captcha')

        if not all([reg_number, dob, captcha]):
            return jsonify({'error': 'All fields are required'}), 400

        # Initialize driver if needed
        init_driver()

        # Make sure we're on the correct page with faster page load
        if 'everify.bdris.gov.bd' not in driver.current_url:
            driver.execute_script('window.stop();')  # Stop any current loading
            driver.get('https://everify.bdris.gov.bd/')
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.ID, 'ubrn'))
                )
            except:
                driver.refresh()  # Retry once if page load fails

        # Fill in the form fields
        driver.execute_script("""
            document.getElementById('ubrn').value = arguments[0];
            document.getElementById('BirthDate').value = arguments[1];
            document.getElementById('CaptchaInputText').value = arguments[2];
        """, reg_number, dob, captcha)

        # Submit the form using JavaScript
        driver.execute_script("""
            document.getElementById('ubrnsearchform').submit();
        """)

        # Wait for either error message or table
        wait = WebDriverWait(driver, 5)
        # First check for error message
        try:
            error_element = driver.find_element(By.CLASS_NAME, 'validation-summary-errors')
            error_msg = error_element.text.strip()
            return jsonify({'error': error_msg})
        except:
            # If no error found, wait for table
            table = wait.until(
                    EC.presence_of_element_located((By.TAG_NAME, 'table'))
                )

            # Extract data using optimized JavaScript
            result_data = driver.execute_script("""
                function extractData() {
                    const data = {};
                    const tables = document.querySelectorAll('table');
                    
                    if (tables.length >= 2) {
                        // Extract registration details
                        const regRows = tables[0].rows;
                        if (regRows.length >= 5) {
                            const regCells = regRows[2].cells;
                            const birthCells = regRows[4].cells;
                            
                            if (regCells.length >= 3) {
                                Object.assign(data, {
                                    'Registration Date': regCells[0].textContent.trim(),
                                    'Registration Office': regCells[1].textContent.trim(),
                                    'Issuance Date': regCells[2].textContent.trim()
                                });
                            }
                            
                            if (birthCells.length >= 3) {
                                Object.assign(data, {
                                    'Date of Birth': birthCells[0].textContent.trim(),
                                    'Birth Registration Number': birthCells[1].textContent.trim(),
                                    'Sex': birthCells[2].textContent.trim()
                                });
                            }
                        }
                        
                        // Extract personal details
                        const persRows = tables[1].rows;
                        for (const row of persRows) {
                            const cells = row.cells;
                            if (cells.length >= 4) {
                                const [keyBengali, valueBengali, keyEnglish, valueEnglish] = 
                                    Array.from(cells).map(cell => cell.textContent.trim());
                                
                                if (keyBengali && valueBengali) data[keyBengali] = valueBengali;
                                if (keyEnglish && valueEnglish) data[keyEnglish] = valueEnglish;
                            }
                        }
                    }
                    // Extract address using XPath
                    try {
                        var addressNode = document.evaluate('/html/body/div[2]/p[2]/span/em', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (addressNode) {
                            let address = addressNode.textContent.trim();
                            if (address.endsWith('.')) {
                                address = address.slice(0, -1).trim(); // remove last "." if exists
                            }
                            data['address'] = address;
                        }
                    } catch (e) {
                        data['address'] = '';
                    }

                    // Extract birthPlaceEn using XPath
                    try {
                        var birthPlaceEnNode = document.evaluate('/html/body/div[2]/div/div[2]/div/table/tbody/tr[2]/td[4]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (birthPlaceEnNode) {
                            data['birthPlaceEn'] = birthPlaceEnNode.textContent.trim();
                        }
                    } catch (e) {
                        data['birthPlaceEn'] = '';
                    }
                    return data;
                }
                return extractData();
            """)

            # Map to desired output structure
            mapped_result_data = map_verification_data(result_data)
            json_str = json.dumps(mapped_result_data, ensure_ascii=False, indent=2)
            session['verification_data'] = json_str
            stats.register_request(success=True)
            # Log user activity for web UI
            details = {
                'nameEn': mapped_result_data.get('nameEn', ''),
                'brn': mapped_result_data.get('brn', ''),
                'dob': mapped_result_data.get('dob', ''),
                'birthPlaceEn': mapped_result_data.get('birthPlaceEn', ''),
                'status': 'Success',
                'endpoint': 'web_submit',
                'method': 'POST',
                'path': '/submit',
                'remote_addr': request.remote_addr,
                'origin': request.headers.get('Origin') or request.headers.get('Referer') or request.remote_addr or 'unknown'
            }
            user_activity.add_activity('web_ui', 'web_submit', details, success=True)
            return jsonify({'redirect': '/result'})
    except Exception as e:
        print(f"Error extracting data: {str(e)}")
        stats.register_request(success=False)
        details = {
            'status': 'Failed',
            'endpoint': 'web_submit',
            'method': 'POST',
            'path': '/submit',
            'remote_addr': request.remote_addr,
            'origin': request.headers.get('Origin') or request.headers.get('Referer') or request.remote_addr or 'unknown',
            'error': str(e)
        }
        user_activity.add_activity('web_ui', 'web_submit', details, success=False)
        return jsonify({'error': 'Could not extract verification data. Please try again.'}), 500

@app.route('/result')
def result():
    json_str = session.get('verification_data')
    if not json_str:
        return redirect('/')
    return render_template('result.html', json_str=json_str)

# API endpoints
@app.route('/api/captcha', methods=['GET'])
@require_api_key
def api_get_captcha():
    try:
        # Initialize driver if needed
        init_driver()
        
        # Navigate to the verification page if needed
        if 'everify.bdris.gov.bd' not in driver.current_url:
            driver.execute_script('window.stop();')
            driver.get('https://everify.bdris.gov.bd/')
        
        # Wait for form and captcha elements
        wait = WebDriverWait(driver, 10)
        try:
            # Wait for key elements
            wait.until(EC.presence_of_element_located((By.ID, 'ubrn')))
            wait.until(EC.presence_of_element_located((By.ID, 'BirthDate')))
            captcha_element = wait.until(EC.presence_of_element_located((By.ID, 'CaptchaImage')))
            
            # Make sure captcha is visible
            if not captcha_element.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView(true);", captcha_element)
                time.sleep(0.5)
            
            # Get captcha screenshot
            captcha_image = captcha_element.screenshot_as_png
            if not captcha_image:
                raise Exception("Captcha screenshot was empty")
            
            # Get captcha token if available
            try:
                captcha_token = driver.find_element(By.ID, 'CaptchaDeText').get_attribute('value')
            except:
                captcha_token = None
            
            # Return the image directly for viewing in browser/photo viewer
            stats.register_request(success=True, endpoint='api_get_captcha')
            response = send_file(
                BytesIO(captcha_image),
                mimetype='image/png',
                as_attachment=False,
                download_name='captcha.png'
            )
            
            # Add the token as a custom header if available
            if captcha_token:
                response.headers['X-Captcha-Token'] = captcha_token
                
            return response
            
        except Exception as e:
            print(f"Error getting captcha elements: {str(e)}")
            # Try refreshing the page once
            driver.refresh()
            time.sleep(2)
            
            # Get captcha screenshot after refresh
            captcha_image = get_captcha_screenshot()
            if captcha_image:
                stats.register_request(success=True)
                return send_file(
                    BytesIO(captcha_image),
                    mimetype='image/png',
                    as_attachment=False,
                    download_name='captcha.png'
                )
            
            stats.register_request(success=False)
            return jsonify({
                'success': False,
                'error': 'Failed to capture captcha after refresh'
            }), 500
            
    except Exception as e:
        print(f"API Error capturing captcha: {str(e)}")
        stats.register_request(success=False)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/verify', methods=['POST'])
@require_api_key
def api_verify():
    global driver
    try:
        data = request.json
        if not data:
            return jsonify({
                'error': 'Request must include JSON data'
            }), 400

        reg_number = data.get('reg_number')
        dob = data.get('dob')
        captcha = data.get('captcha')

        if not all([reg_number, dob, captcha]):
            return jsonify({
                'error': 'Missing required fields: reg_number, dob, and captcha are required'
            }), 400

        # Initialize driver if needed
        init_driver()

        # Make sure we're on the correct page
        if 'everify.bdris.gov.bd' not in driver.current_url:
            driver.execute_script('window.stop();')
            driver.get('https://everify.bdris.gov.bd/')
            try:
                # Wait for form elements to be present
                wait = WebDriverWait(driver, 5)
                wait.until(EC.presence_of_element_located((By.ID, 'ubrn')))
                wait.until(EC.presence_of_element_located((By.ID, 'BirthDate')))
                wait.until(EC.presence_of_element_located((By.ID, 'CaptchaInputText')))
                wait.until(EC.presence_of_element_located((By.ID, 'ubrnsearchform')))
            except Exception as e:
                print(f"API Error loading page: {str(e)}")
                stats.register_request(success=False)
                return jsonify({
                    'success': False,
                    'error': 'Failed to load verification page'
                }), 500

        # Fill out and submit the form
        try:
            driver.execute_script(f"""
                document.getElementById('ubrn').value = '{reg_number}';
                document.getElementById('BirthDate').value = '{dob}';
                document.getElementById('CaptchaInputText').value = '{captcha}';
                var form = document.getElementById('ubrnsearchform');
                if (form) {{
                    var submitButton = form.querySelector('input[type="submit"]');
                    if (submitButton) {{
                        submitButton.click();
                    }} else {{
                        form.submit();
                    }}
                }}
            """)
        except Exception as e:
            print(f"API Error submitting form: {str(e)}")
            stats.register_request(success=False)
            return jsonify({
                'success': False,
                'error': 'Failed to submit form'
            }), 500

        # Wait for either error message or table
        wait = WebDriverWait(driver, 5)
        try:
            # First check for error message
            try:
                error_element = driver.find_element(By.CLASS_NAME, 'validation-summary-errors')
                error_msg = error_element.text.strip()
                stats.register_request(success=False)
                return jsonify({
                    'success': False,
                    'error': error_msg
                })
            except:
                # If no error found, wait for table
                table = wait.until(
                    EC.presence_of_element_located((By.TAG_NAME, 'table'))
                )

            # Extract data using optimized JavaScript
            result_data = driver.execute_script("""
                function extractData() {
                    const data = {};
                    const tables = document.querySelectorAll('table');
                    
                    if (tables.length >= 2) {
                        // Extract registration details
                        const regRows = tables[0].rows;
                        if (regRows.length >= 5) {
                            const regCells = regRows[2].cells;
                            const birthCells = regRows[4].cells;
                            
                            if (regCells.length >= 3) {
                                Object.assign(data, {
                                    'Registration Date': regCells[0].textContent.trim(),
                                    'Registration Office': regCells[1].textContent.trim(),
                                    'Issuance Date': regCells[2].textContent.trim()
                                });
                            }
                            
                            if (birthCells.length >= 3) {
                                Object.assign(data, {
                                    'Date of Birth': birthCells[0].textContent.trim(),
                                    'Birth Registration Number': birthCells[1].textContent.trim(),
                                    'Sex': birthCells[2].textContent.trim()
                                });
                            }
                        }
                        
                        // Extract personal details
                        const persRows = tables[1].rows;
                        for (const row of persRows) {
                            const cells = row.cells;
                            if (cells.length >= 4) {
                                const [keyBengali, valueBengali, keyEnglish, valueEnglish] = 
                                    Array.from(cells).map(cell => cell.textContent.trim());
                                
                                if (keyBengali && valueBengali) data[keyBengali] = valueBengali;
                                if (keyEnglish && valueEnglish) data[keyEnglish] = valueEnglish;
                            }
                        }
                    }
                    // Extract address using XPath
                    try {
                        var addressNode = document.evaluate('/html/body/div[2]/p[2]/span/em', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (addressNode) {
                            data['address'] = addressNode.textContent.trim();
                        }
                    } catch (e) {
                        data['address'] = '';
                    }
                    // Extract birthPlaceEn using XPath
                    try {
                        var birthPlaceEnNode = document.evaluate('/html/body/div[2]/div/div[2]/div/table/tbody/tr[2]/td[4]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (birthPlaceEnNode) {
                            data['birthPlaceEn'] = birthPlaceEnNode.textContent.trim();
                        }
                    } catch (e) {
                        data['birthPlaceEn'] = '';
                    }
                    return data;
                }
                return extractData();
            """)

            # Map to desired output structure
            mapped_result_data = map_verification_data(result_data)
            json_data = json.dumps({'success': True, 'data': mapped_result_data}, ensure_ascii=False)
            # Log user activity for API verify with all details
            from models import user_activity
            details = {
                'nameEn': mapped_result_data.get('nameEn', ''),
                'brn': mapped_result_data.get('brn', ''),
                'dob': mapped_result_data.get('dob', ''),
                'birthPlaceEn': mapped_result_data.get('birthPlaceEn', ''),
                'status': 'Success',
                'endpoint': 'api_verify',
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'origin': request.headers.get('Origin') or request.headers.get('Referer') or request.remote_addr or 'unknown'
            }
            user_activity.add_activity(request.headers.get('X-API-KEY'), 'api_verify', details, success=True)
            return Response(json_data, mimetype='application/json')
        except Exception as e:
            print(f"API Error extracting data: {str(e)}")
            stats.register_request(success=False)
            return jsonify({
                'success': False,
                'error': 'Could not extract verification data'
            }), 500
    except Exception as e:
        print(f"API Error in verify: {str(e)}")
        stats.register_request(success=False)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def cleanup():
    global driver
    if driver:
        try:
            driver.quit()
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
        finally:
            driver = None

if __name__ == '__main__':
    try:
        # Initialize the driver once at startup
        init_driver()
        app.run(port=5000, debug=False)
    except Exception as e:
        print(f"Error starting server: {str(e)}")
    finally:
        cleanup()
