Battlestar Goursica
===================

Source control visualization for your organization.

Requirements
==============================

- Python >= 2.7.2
- Pip >= 0.8.3
- python-dateutil == 1.5
- clint == 0.3

Usage
==============================

	git clone git@github.com:ff0000/battlestar-goursica.git
	cd battlestar-goursica
	pip install -r requirements.txt
	python adama.py

Follow the instructions on first-run to set your default credentials.

Server Recommendations
==============================

- Ubuntu >= 11.10
	- apt-get install:
		- xmonad
		- sox
		- python-tk
		- xdotool

Server Setup
==============================

- Download and install [Ubuntu Latest](http://www.ubuntu.com/download/ubuntu/download)
- Launch the Update Manager. Get yourself up to date.
- Launch the Terminal.
- Install the required Ubuntu tools:
	- `sudo apt-get install sox python-tk xdotool`
- Install & Update Pip
	- `sudo apt-get install python-pip`
	- `sudo pip install --upgrade pip`
- Update Git:
	- `sudo apt-get install git-core`
- Download Battlestar Goursica:
	- `git clone git@github.com:doctyper/battlestar-goursica.git`
- Install BSG requirements:
	- `cd battlestar-goursica`
	- `sudo pip install -r requirements.txt`
- All set! Run Battlestar Goursica:
	- `./adama.py`

## User Authentication (optional)

In order to use a user/pass for BSG, you must also set up an SSH key for GitHub to authenticate the user. Follow [this online guide](http://help.github.com/linux-set-up-git/) to get that up and running.

## Xmonad

- Install XMonad
	- `sudo apt-get install xmonad`
- Log out of Ubuntu.
- At the login screen, click the cog next to your user and select 'XMonad'.
- Log in.
- [To be continued]

Avoiding Screen Burn-in
==============================

If, like us, you're using a screen susceptible to screen burn in, you can run this optional cron job to auto-cycle each window on a 5 minute timer.

	$ crontab -e

Add this to your crontab:

	*/5 * * * * /path/to/battlestar-goursica/cycle.py 2> /path/to/battlestar.log
