from pyppeteer import launch
import asyncio
import requests
import os
from os import environ
from tqdm import tqdm
import random
import argparse
import datetime
import threading



async def download(url, pathname):
    # download the body of response by chunk, not immediately
    response = requests.get(url, stream=True)

    # get the total file size (max of progress bar)
    file_size = int(response.headers.get("Content-Length", 0))

    # get the file name
    file_obj_name = url.split("/")[-1]
    image_extensions = ['.jpg', '.png', '.jpeg']
    if any(extension in url.split("/")[-1] for extension in image_extensions):
        filename = os.path.join(pathname, url.split("/")[-1])
    else:
        print("Garbage------> " + file_obj_name)
        return True
    
    # progress bar, changing the unit to bytes instead of iteration (default by tqdm)
    progress = tqdm(response.iter_content(1024), f"Downloading {file_obj_name}", total=file_size, unit="B", unit_scale=True, unit_divisor=1024)
    with open(filename, "wb") as f:
        try:
            for data in progress:
                try:
                    # write data read to the file
                    f.write(data)
                    # update the progress bar manually
                    progress.update(len(data))
                except Exception as e:
                    print("Error downloading: " + url + ", because: " + e)
                    break
        except:
            print('Error downloading image' + file_obj_name)
            pass
        else:
            RUNTIME_STORAGE.number_of_downloads += 1
        
        return True

async def load_and_validate_image(thumbnail, page, number_of_files_in_folder, max_number, pathname, delay):
    try:
        # Check if we've reached our maximum number of images in folder
        if number_of_files_in_folder < max_number:

            # click the a tag instead of the parent object
            actual_click = await page.evaluateHandle(
                '(thumbnail) => thumbnail.querySelector("a")',
                thumbnail
            )
            # Click on the thumbnail to expand the full image
            await actual_click.click()

            # Wait for Google to finish serving the image, added variance for fun (if you lower this value, your success rate of downloads will be lower)
            random_sleep = random.uniform(delay, delay+0.3)
            await asyncio.sleep(random_sleep)                

            # Get large version of image after clicking on thumbnail
            image_images = await page.querySelectorAll('.n3VNCb')

            # Discard any elements without valid download links, then download
            for item in image_images:
                check = await page.evaluate(
                '(item) => item.src',
                item    
                )
                if 'http' in str(check):
                    pass
                else:
                    continue
                
                # Get rid of the garbage after the .extension in the url 
                image_src = check.split("?")[0]
                
                # Check to make sure it's of one of the extensions I want
                image_extensions = ['.jpg', '.png', '.jpeg']
                if any(extension in str(image_src) for extension in image_extensions):
                    # Download image to save directory
                    await download(image_src, pathname)
    except Exception as e:
        print("Error in download_image(): " + str(e))
        return False

    return True

# loop through range asynchronously
async def asyncrange(count):
    for i in range(count):
        yield(i)

# Launch a pyppeteer window to navigate to google image search page, then attempt to download max_number of images
async def find_images(search_term, max_number, save_path, delay, start_time):
    max = max_number[0]
    print('===============================================================================')
    print('Attempting to download {} pictures of "{}" to {}'.format(max, search_term, save_path))
    print('===============================================================================')
    browser = await launch(
        headless=False,
        args=['--window-size=1200,800'],
        defaultViewport=None
    )
    page = await browser.newPage()
    await page.goto('https://images.google.com')
    await page.type('input[title="Search"]', search_term)
    await page.click('button[type=submit]')
    await page.waitForNavigation()

    # if path doesn't exist, create the save folder
    if not os.path.isdir(save_path):
        os.makedirs(save_path)


    # Attempt to download pictures a {max_number} of times, loop asynchronously 
    async for i in asyncrange(max-1):   
        # get current thumbnail ElementHandle from persistent local storage
        current_thumbnail = RUNTIME_STORAGE.current_thumbnail
        
        if not current_thumbnail:
            try:
                # This gets the first thumbnail on the page
                current_thumbnail = await page.querySelector('.isv-r.PNCib')
                # current_thumbnail = await page.querySelector('.islrc img.rg_i')
            except:
                # If we can't find it
                raise Exception('Can not find the first thumbnail, quitting')
                break

        try:
            number_of_downloads = RUNTIME_STORAGE.number_of_downloads

            # Create a new parallel task to download the image 
            await asyncio.create_task(load_and_validate_image(current_thumbnail, page, number_of_downloads, max, save_path, delay))
        except Exception as e:
            print("Error finding image: " + str(e))
            break   
        finally:
            # Attempt to find the next thumbnail based on the current element
            try:
                # Get the next thumbnail in the dom, if it's one of Google's "suggested search" thumbnails, skip it
                next_thumbnail = await page.evaluateHandle(
                    '(current_thumbnail) => { \
                        if (current_thumbnail.nextElementSibling.hasAttribute("jsaction")) \
                        { \
                            return current_thumbnail.nextElementSibling; \
                        } \
                        else { \
                            return current_thumbnail.nextElementSibling.nextElementSibling; \
                        } \
                    }',
                    current_thumbnail
                )
                # Set the current thumbnail to the next one in the DOM
                RUNTIME_STORAGE.current_thumbnail = next_thumbnail
            except Exception as e:
                print('Error in evaluating the next thumbnail in the DOM' + str(e))
            
    # Get final number of images downloaded to save directory
    number_of_downloads = len(os.listdir(save_path))

    # Calculate success rate of download attempts
    decimal_success = round(number_of_downloads/max * 100, 2)
    success_rate = str(decimal_success) + "%"

    # Calculate total size of all images downloaded
    total_size=0.0
    for path, dirs, files in os.walk(save_path):
        for f in files:
            fp = os.path.join(path, f)
            total_size += os.path.getsize(fp)

    # Get size in MB
    megabytes = str(round(total_size/1000000, 2)) + " MB"

    # Calculate time it took to finish
    end_time = datetime.datetime.now()
    total_seconds = str(round((end_time-start_time).total_seconds(), 1))
    print('===============================================================================')
    print('Oh snap-- I downloaded {} pictures of "{}" to "{}", a total of {} over {} seconds. I successfully downloaded a picture {} of the time!'.format(number_of_downloads, search_term, save_path, megabytes, total_seconds, success_rate))
    print('===============================================================================')
    await browser.close()
    


# Instantiate RUNTIME_STORAGE, which is persistent local storage outside the asyncio loop
RUNTIME_STORAGE = threading.local()
RUNTIME_STORAGE.current_thumbnail = None
RUNTIME_STORAGE.number_of_downloads = 0

# Parse command line variables
pictures_default_location = os.path.join(environ["USERPROFILE"], "Pictures")
parser = argparse.ArgumentParser(description="Attempt to download a {max} # of images from Google Images using: {searchterm}; Only supports .jpg, .png, and .jpeg; If you do not include a save location it will default to a new folder in your user's picture folder")
parser.add_argument('--max', metavar='(int)', type=int, nargs='+', help='Max number of images to be downloaded (defaults to 50)')
parser.add_argument('--searchterm', metavar='(string)', type=str, help='Term to search for')
parser.add_argument('--savedir', metavar='(string)', type=str, help="Location to create folder named {searchterm} (if not assigned, defaults to your user's pictures folder")
parser.add_argument('--delay', metavar='(float)', type=float, help="Number of seconds to wait for Google to serve images, if your success rate is low set this to 1.0 or higher (defaults to 0.3)")
args = parser.parse_args()
search_term = args.searchterm
start_time = datetime.datetime.now()

if args.max == None:
    max_number = [50]
else:
    max_number = args.max

if args.delay == None:
    delay = 0.3
else:
    delay = args.delay
    
try:
    save_directory = args.savedir
    save_path = os.path.join(save_directory,search_term)
except:
    save_directory = pictures_default_location
    save_path = os.path.join(save_directory,search_term)
# Kick off program here
loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(find_images(search_term, max_number, save_path, delay, start_time))  
except KeyboardInterrupt:
    print("Received exit, exiting")
    # find all futures/tasks still running and wait for them to finish
    pending_tasks = [
        task for task in asyncio.Task.all_tasks() if not task.done()
    ]
    print(pending_tasks)
    tasks = loop.run_until_complete(asyncio.gather(*pending_tasks))
    tasks.cancel()
    tasks.exception()
    loop.close()

