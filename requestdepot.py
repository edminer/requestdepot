#!/usr/local/bin/python -u

# https://python-twitter.readthedocs.io/en/latest/twitter.html
# https://dev.twitter.com/rest/direct-messages/getting-started

import sys,os,logging,re,traceback
sys.path.append("/usr/local/bin/pymodules")
from genutil import EXENAME,EXEPATH,GeneralError
import genutil

# Import the special modules we'll need
import json, time
import twitter
import RPi.GPIO as GPIO

#------------------------------------------------------------------------------
# GLOBALS
#------------------------------------------------------------------------------

logger=logging.getLogger(EXENAME)

G_api = None
G_authorizedSenders = []

#------------------------------------------------------------------------------
# USAGE
#------------------------------------------------------------------------------

def usage():
   from string import Template
   usagetext = """

 $EXENAME

 Function: Watch for incoming requests (twitter DM) and farm out the work to the appropriate
           tool/module.

 Syntax  : $EXENAME {--debug #}

 Note    : Parm         Description
           ----------   --------------------------------------------------------

           --debug      optionally specifies debug option
                        0=off 1=STDERR 2=FILE

 Examples: $EXENAME

 Change History:
  em  03/12/2017  first written
  em  05/14/2017  reworked with Twitter DM
.
"""
   template = Template(usagetext)
   return(template.substitute({'EXENAME':EXENAME}))


#------------------------------------------------------------------------------
# Subroutine: main
# Function  : Main routine
# Parms     : none (in sys.argv)
# Returns   : nothing
# Assumes   : sys.argv has parms, if any
#------------------------------------------------------------------------------
def main():

   ##############################################################################
   #
   # Main - initialize
   #
   ##############################################################################

   initialize()
   global G_api
   global G_authorizedSenders

   ##############################################################################
   #
   # Logic
   #
   ##############################################################################

   try:

      # We only want 1 instance of this running.  So attempt to get the "lock".
      genutil.getLock(EXENAME)

      api = twitter.Api(consumer_key=G_config["twitterAccount"]["consumerKey"],
                        consumer_secret=G_config["twitterAccount"]["consumerSecret"],
                        access_token_key=G_config["twitterAccount"]["accessToken"],
                        access_token_secret=G_config["twitterAccount"]["accessTokenSecret"],
                        sleep_on_rate_limit=True)

      print("Getting list of authorized senders (Twitter 'frineds').")
      users = api.GetFriends()
      for u in users:
         print("Friend:", u.name, u.id, u.screen_name)
         G_authorizedSenders.append(u.id)

      # Get the id of the most current message
      messages = api.GetDirectMessages(count=1)
      lastMesssageId = messages[0].id

      print("Entering forever loop of checking for new messages and acting on them")
      # Note: some day when the Activity API is out of beta and supported by the twitter module, I'd like to replace
      #       the following loop with the Activity API
      while True:

         print("Checking for new messages.")
         messages = api.GetDirectMessages(since_id=lastMesssageId)

         if messages:
            for message in list(reversed(messages)):
               print(message.id, message.text, message.sender.id)
               lastMesssageId = message.id
               messageText = message.text.strip().lower()

               if message.sender.id in G_authorizedSenders:
                  if messageText.startswith("take photo") or messageText.startswith("take video"):
                     snapType = ("video","photo")["photo" in messageText]
                     match = re.search(r'^\S+ \S+ (\S+)', messageText)
                     if match:
                        emailTo = match.group(1)
                     else:
                        emailTo = G_config["snapandtell"]["emailTo"]
                     returncode, out, err = genutil.execCommand("/usr/local/src/snapandtell/snap_and_tell.py --light %s %s" % (snapType, emailTo))
                     if returncode == 0:
                        api.PostDirectMessage("Received and Completed: %s" % message.text, user_id=message.sender.id, screen_name=None)
                     else:
                        logger.info("%s: %d, %s, %s" % (messageText, returncode, out, err))
                        api.PostDirectMessage("Received and Failed: %s" % message.text, user_id=message.sender.id, screen_name=None)
                  elif messageText == "light on" or messageText == "light off":
                     lightSetting = (1,0)[" on" in messageText]
                     GPIO.setwarnings(False)
                     GPIO.setmode(GPIO.BOARD)
                     GPIO.setup(12, GPIO.OUT)
                     GPIO.output(12,lightSetting)
                     api.PostDirectMessage("Received and Completed: %s" % message.text, user_id=message.sender.id, screen_name=None)
                  else:
                     api.PostDirectMessage("Hints: take photo {<email>}, take video {<email>}, light on|off", user_id=message.sender.id, screen_name=None)
               else:
                  print("Ignoring message from unauthorized sender: %d", message.sender.id)
         else:
            print("No new messages.  Sleeping for %d seconds..." % G_config["sleepCycle"])
            time.sleep(G_config["sleepCycle"])

   except GeneralError as e:
      if genutil.G_options.debug:
         # Fuller display of the Exception type and where the exception occured in the code
         (eType, eValue, eTraceback) = sys.exc_info()
         tbprintable = ''.join(traceback.format_tb(eTraceback))
         genutil.exitWithErrorMessage("%s Exception: %s\n%s" % (eType.__name__, eValue, tbprintable), errorCode=e.errorCode)
      else:
         genutil.exitWithErrorMessage(e.message, errorCode=e.errorCode)

   except Exception as e:
      if genutil.G_options.debug:
         # Fuller display of the Exception type and where the exception occured in the code
         (eType, eValue, eTraceback) = sys.exc_info()
         tbprintable = ''.join(traceback.format_tb(eTraceback))
         genutil.exitWithErrorMessage("%s Exception: %s\n%s" % (eType.__name__, eValue, tbprintable))
      else:
         genutil.exitWithErrorMessage(str(e))

   ##############################################################################
   #
   # Finish up
   #
   ##############################################################################

   logger.info(EXENAME+" exiting")
   logging.shutdown()

   exit()


#------------------------------------------------------------------------------
# Subroutine: initialize
# Function  : performs initialization of variable, CONSTANTS, other
# Parms     : none
# Returns   : nothing
# Assumes   : ARGV has parms, if any
#------------------------------------------------------------------------------
def initialize():

   # PROCESS COMMAND LINE PARAMETERS

   import argparse  # http://www.pythonforbeginners.com/modules-in-python/argparse-tutorial/

   parser = argparse.ArgumentParser(usage=usage())
   parser.add_argument('--debug', dest="debug", type=int, help='0=no debug, 1=STDERR, 2=log file')

   genutil.G_options = parser.parse_args()

   if genutil.G_options.debug == None or genutil.G_options.debug == 0:
      logging.disable(logging.CRITICAL)  # effectively disable all logging
   else:
      if genutil.G_options.debug == 9:
         genutil.configureLogging(loglevel='DEBUG')
      else:
         genutil.configureLogging()

   global G_config
   G_config = genutil.processConfigFile()

   logger.info(EXENAME+" starting:"+__name__+" with these args:"+str(sys.argv))

# Standard boilerplate to call the main() function to begin the program.
if __name__ == "__main__":
   main()

