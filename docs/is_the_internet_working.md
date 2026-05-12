Have you ever?

    Been navigating to webpage that seems to load as slow as it could
    Been listening to Spotify and your music keeps skipping
    Been starring at the infamous YouTube load screen

gfycat.com

If you answered yes to any of the previous statements you may be suffering from “iS tHe InTerNet WORkinG [Insert name]!?”

As everyone continues to work and learn from home in the COVID-19 pandemic, I am sure everyone can agree, there are no shortages of hiccups in network performance. How many times have you visited speedtest.net to check your network performance? Well I can tell you,
Press enter or click to view image in full size

Frustrated with checking speedtest.net every 5min, I wanted a way to monitor bandwidth usage over time and see if my performance had changed. I wanted to run speed test automatically, to captured information and then display it over a time series graph. I then found speedtest.cli and was noticing a number of posts involving the use of a Raspberry pi, specifically this one. This was prefect as I had an extra Raspberry Pi 3b+ model on hand and wanted to put it to good use. As I started to follow his tutorial, I realized I needed some “prerequisites”. Luckily he had a previous posting that walked you through. I followed most of his tutorial but wanted to make note of some observations and changes that I made.
Write on Medium

First installing InfluxDB and Grafana on my RPI(raspberry pi). This was pretty straight forward, although he was not specific with the command syntax when creating a user in InfluxDB 1.8.0. After a little research I found that InfluxDB has a extremely in-depth user guide. I followed there guide on authentication and authorization in influxdb to successfully create the user I wanted. The command was simple,

CREATE USER admin WITH PASSWORD '<password>' WITH ALL PRIVILEGES
pi@raspberrypi:~/projet_Speed $ CREATE USER grafana WITH PASSWORD 'notmyrealpassword' WITH ALL PRIVILEGES 

After that I was then able to move on and install Grafana and attach Influx as a data source. I then transitioned to his regular network speed tests portion of his article and proceeded to follow the rest of his instructions. I started to run into errors with his ‘rpi-speedtest-influx.py’ script. It took me hours just to realize I had python version 3 and his script was written in python. As my math teacher once said,

    haste makes waste, and PAY ATTENTION TO DETAIL!

#!/usr/bin/env python
vs 
#!/usr/bin/env python3

Once I fix this issue things started to fall back into place. I ran the script successfully and saw its result in the corresponding database. I quickly set up the cron job, made sure it was running successfully, and proceeded to use his sample dashboard for Grafana. All seemed well as I had one data point on the graph and the cron job was set to every 15min. Now all that was left was waiting.

I got extremely frustrated as 2 hours past and nothing had changed. I frantically started to backtrack, fixing things that weren't broken. I finally went back to the GitHub page were the author posted the dashboard for grafana and found a comment that solved all my problems. The author neglected to change all of the “measurement” names from “speed” to “speedtest” when writing the Json file.
Here’s what it was
Press enter or click to view image in full size
Here is what it needs to be

Once I changed all the instances when the word “speed” was found to “speedtest”, I manually ran the rpi-speedtest-influx.py and another data point poped up on my graph! It works!……sorta….

In my next article I will explain the improvements I made to the script(rpi-speedtest-influx.py) and the over all process of this project.
