Most students are learning how to cope with remote learning during this pandemic. Research shows that everyone learns differently. My professor records audio PowerPoint presentations that cover chapters and contain “code words”. The “code words” are required to be emailed back to him as it is used for attendance. While I appreciate the professor’s efforts, I personally tend to absorb material better when I am able to read and highlight certain aspects within a chapter. I had completed the required assignments for the chapter and wanted to move onto the next subject. This is when I began to look at ways of obtaining the “code words”, without spending an hour listening to the professor’s previous lectures.

Easier said then done.

I will spare you the elongated version of all the research I did by summarizing my journey. I found an open source speech recognition and voice synthesis project and the following is a complete listing of the work I did to demonstrate the transcription and the implementation of the algorithm.

Lets get started.

First, lets navigate to: https://github.com/mozilla/DeepSpeech. This is where most information can be found about the project. Along with project information, there is a short tutorial regarding the use of DeepSpeech. Next, we can start by taking a look at the Pre-trained model system requirements as this varies person to person.
Press enter or click to view image in full size

There are four options available when choosing clients/language bindings. I chose to use the Python package/language binding simply because it was the first option along with the recognition of python’s versatility.

Installing system requirements:

The only system requirements I installed was sox.

$ brew install sox

Basic understanding:

Moving along, to get a basic understanding of the process, I followed the instructions provided by Project DeepSpeech with a pre-trained model

I navigated to: ~/Documents/

 $ mkdir “RenameAsAWorkSpace” — In this case my workspace is called “TextoSpeechTest”
$ cd  ~/Documents/TextoSpeechTest
$ virtualenv -p python3 $HOME/tmp/deepspeech-venv/
-bash: virtualenv: command not found

Shoot! So as it turns out, virtualenv is a prerequisite aswell! So naturally, I tried: Brew install virtualenv.

$ brew install virtualenv
Error: No available formula with the name "virtualenv" 
==> Searching for a previously deleted formula (in the last month)...
Warning: homebrew/core is shallow clone. To get complete history run:
  git -C "$(brew --repo homebrew/core)" fetch --unshallow

Error: No previously deleted formula found.
==> Searching for similarly named formulae...
These similarly named formulae were found:
pyenv-virtualenv                                             pyenv-virtualenvwrapper
To install one of them, run (for example):
  brew install pyenv-virtualenv
==> Searching taps...
==> Searching taps on GitHub...
Error: No formulae found in taps.

No luck!

I continued to read the documentation on the DeepSpeech project and ran across a hyperlink that showed me what virtualenv was and how to install it.

$ pip3 install virtualenv

After you’ve installed virtualenv, we can finally move on.

$ virtualenv -p python3 $HOME/tmp/deepspeech-venv/
created virtual environment CPython3.7.7.final.0-64 in 355ms
  creator CPython3Posix(dest= ~/tmp/deepspeech-venv, clear=False, global=False)
  seeder FromAppData(download=False, pip=latest, setuptools=latest, wheel=latest, via=copy, app_data_dir= ~/Library/Application Support/virtualenv/seed-app-data/v1.0.1)
  activators BashActivator,CShellActivator,FishActivator,PowerShellActivator,PythonActivator,XonshActivator

Success!

Here’s what that command does: A “tmp” folder is created wherever $HOME is assigned along with a “deepspeech-venv” folder. Within “deepspeech-venv” are essential python executables for any python project.

Next we run:

$ source $HOME/tmp/deepspeech-venv/bin/activate 

This essentially “activates” a virtual environment within ~/tmp/deepspeech-venv/bin/ with all the bells and whistles.

~/tmp/deepspeech-venv/bin/
$ ls
activate        activate.xsh        easy_install-3.7    f2py3.7            pip3.7            wheel
activate.csh        activate_this.py    easy_install3        pip            python            wheel-3.7
activate.fish        deepspeech        f2py            pip-3.7            python3            wheel3
activate.ps1        easy_install        f2py3            pip3            python3.7

After our previous command, our command line should have (deepspeech-venv)$

Now we use curl to download and extract a pre-trained English model:

(deepspeech-venv)$ curl -LO https://github.com/mozilla/DeepSpeech/releases/download/v0.6.1/deepspeech-0.6.1-models.tar.gz
(deepspeech-venv)$ tar xvf deepspeech-0.6.1-models.tar.gz

Next we download and extract example audio files:

(deepspeech-venv)$ curl -LO https://github.com/mozilla/DeepSpeech/releases/download/v0.6.1/audio-0.6.1.tar.gz
(deepspeech-venv)$ tar xvf audio-0.6.1.tar.gz

Now we are ready to see what this AI can do!
Become a Medium member

Transcribe the audio file:

(deepspeech-venv)$ deepspeech —-model deepspeech-0.6.1-models/output_graph.pbmm —-audio audio/2830–3980–0043.wav
Loading model from file deepspeech-0.6.1-models/output_graph.pbmm
TensorFlow: v1.14.0-21-ge77504ac6b
DeepSpeech: v0.6.1-0-g3df20fe
2020-04-21 17:00:07.050215: I tensorflow/core/platform/cpu_feature_guard.cc:142] Your CPU supports instructions that this TensorFlow binary was not compiled to use: AVX2 FMA
Loaded model in 0.0427s.
Running inference.
experience proofsless
Inference took 1.985s for 1.975s audio file.

NICE! We got it working! “Experience proves this”

Lets save this output to a file called “Test”

(deepspeech-venv)$ deepspeech --model deepspeech-0.6.1-models/output_graph.pbmm  --audio audio/2830-3980-0043.wav > Test
Loading model from file deepspeech-0.6.1-models/output_graph.pbmm
TensorFlow: v1.14.0-21-ge77504ac6b
DeepSpeech: v0.6.1-0-g3df20fe
2020-04-21 17:16:11.151475: I tensorflow/core/platform/cpu_feature_guard.cc:142] Your CPU supports instructions that this TensorFlow binary was not compiled to use: AVX2 FMA
Loaded model in 0.0324s.
Running inference.
Inference took 1.946s for 1.975s audio file.
(deepspeech-venv)$ ls
audio                deepspeech-0.6.1-models
Test                audio-0.6.1.tar.gz        deepspeech-0.6.1-models.tar.gz
(deepspeech-venv)$ cat Test
experience proofsless

Cool!!

Now that we have successfully ran our first DeepSpeech model lets get into how I applied it to my homework.

$ Do_my_homework.py

After I finished successfully running DeepSpeech my next challenge was figuring out how to strip a presentation of its audio.

I downloaded the presentation and it was in my downloads folder, but I wanted to keep tabs on the presentations contents so…

I navigated to: ~/Downloads/

$ mkdir "PPT_audio" 
$ cd ~/Downloads/"PPT_audio"
$ mkdir "NameOfPPT" 
$ cd ~/Downloads/
$ mv ".pptx" ~/Downloads/"PPT_audio"/"NameOfPPT"

Making this directory will allow us to separate multiple presentations (basically stay organized).

I learned that simply using “unzip” in a terminal window, will strip the presentation of its contents including the audio.

~/Downloads/"PPT_audio"/"NameOfPPT"
$ unzip ".pptx'
$ ls 
.pptx    docProps
[Content_Types].xml                    ppt
_rels
$ cd ppt/
$ cd media/
$ ls 
image1.jpeg    image18.jpeg    image7.jpeg    media15.m4a    media23.m4a    media31.m4a    media4.m4a    media48.m4a    media56.m4a    media7.m4a
image10.jpeg    image19.png    image8.jpeg    media16.m4a    media24.m4a    media32.m4a    media40.m4a    media49.m4a    media57.m4a    media8.m4a
image11.jpeg    image2.png    image9.jpeg    media17.m4a    media25.m4a    media33.m4a    media41.m4a    media5.m4a    media58.m4a    media9.m4a
image12.jpeg    image20.png    media1.m4a    media18.m4a    media26.m4a    media34.m4a    media42.m4a    media50.m4a    media59.m4a
image13.jpeg    image21.jpeg    media10.m4a    media19.m4a    media27.m4a    media35.m4a    media43.m4a    media51.m4a    media6.m4a
image14.jpeg    image3.jpeg    media11.m4a    media2.m4a    media28.m4a    media36.m4a    media44.m4a    media52.m4a    media60.m4a
image15.jpeg    image4.jpeg    media12.m4a    media20.m4a    media29.m4a    media37.m4a    media45.m4a    media53.m4a    media61.m4a
image16.jpeg    image5.jpeg    media13.m4a    media21.m4a    media3.m4a    media38.m4a    media46.m4a    media54.m4a    media62.m4a
image17.jpeg    image6.jpeg    media14.m4a    media22.m4a    media30.m4a    media39.m4a    media47.m4a    media55.m4a    media63.m4a

Perfect!! We have the audio files! My audio files came in increments; there were 63 of them.

Right! So lets move an audio file into: ~/Documents/TextoSpeechTest/audio; test this AI!

(deepspeech-venv)$ deepspeech --model deepspeech-0.6.1-models/output_graph.pbmm  --audio audio/media"4".m4a 
Loading model from file deepspeech-0.6.1-models/output_graph.pbmm
TensorFlow: v1.14.0-21-ge77504ac6b
DeepSpeech: v0.6.1-0-g3df20fe
2020-04-21 17:21:56.631171: I tensorflow/core/platform/cpu_feature_guard.cc:142] Your CPU supports instructions that this TensorFlow binary was not compiled to use: AVX2 FMA
Loaded model in 0.0139s.
Traceback (most recent call last):
  File "~/tmp/deepspeech-venv/bin/deepspeech", line 8, in <module>
    sys.exit(main())
  File "~/tmp/deepspeech-venv/lib/python3.7/site-packages/deepspeech/client.py", line 126, in main
    fin = wave.open(args.audio, 'rb')
  File "/usr/local/opt/python/Frameworks/Python.framework/Versions/3.7/lib/python3.7/wave.py", line 510, in open
    return Wave_read(f)
  File "/usr/local/opt/python/Frameworks/Python.framework/Versions/3.7/lib/python3.7/wave.py", line 164, in __init__
    self.initfp(f)
  File "/usr/local/opt/python/Frameworks/Python.framework/Versions/3.7/lib/python3.7/wave.py", line 131, in initfp
    raise Error('file does not start with RIFF id')
wave.Error: file does not start with RIFF id

SHOOT! Wait, “file does not start with RIFF id” okay…. So I ran

~/Documents/TextoSpeechTest/audio
$ file * 
2830-3980-0043.wav:   RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 16000 Hz
4507-16021-0012.wav:  RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 16000 Hz
8455-210777-0068.wav: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 16000 Hz

Okay, so I am assuming that this model has specific parameters that need to be met in order for it to recognize audio and transcribe it. Again, eaiser said then done. First, I wanted to figure out a way to combine my 63 audio files to make the conversion process easier. I ended up using iMovie to combine them(finally a use for preinstalled apps!). I threw all the audio files(media*.m4a) from ~/Downloads/”PPT_audio”/”NameOfPPT”/ppt/media ,drag and drop style(Finder), into a new iMovie project and proceed to save it as “media.mp4”.

My next issue was converting .mp4 to .wav and fitting into all the parameters required by DeepSpeech. Once again I will save you the painstaking process of finding such application, I stumbled across To WAV Converter.

I converted the saved iMovie project using To WAV Converter with all the prerequisites( RIFF (little-endian) data, WAVE audio, 16 bit, mono 16000 Hz) and saved it as “media.wav”

I then moved media.wav to: ~/Documents/TextoSpeechTest/audio

FINALLY!!! Lets see if this works! Going back to our (deepspeech-venv) terminal window:

(deepspeech-venv)$ deepspeech --model deepspeech-0.6.1-models/output_graph.pbmm --audio audio/media.wav > "outPutFile".txt 

Being the impatient person I am, I expected to see some sort of output right away. 10min in…..nothing…….15min…nothing

But then I remembered “Inference took 1.946s for 1.975s audio file.” Basically if the media.wav file was an hour long it would take about an hour to transcribe it. I was growing impatient so I opened two terminal windows. I ran “tail” on the output file in one window, and ran “top” in the other.

$ cd ~/Documents/TextoSpeechTest
$ tail "outPutFile".txt

Still nothing…. I was getting nervous, so I ran:

$ top 

Long be hold there it was eating up my CPU. I lept out of my chair in excitement! Now all that was left, hurry up and wait.

Command + f is your friend:

Finally, after about an hour, the “tail” terminal window spit out thousands of words.

I navigated to the output file using Finder. Double clicked the “outPutFile”.txt and there it was. Words, and lots of them. The first thing I noticed, probably the most obvious, was the AI spelled words like a 3rd grader. For example, “experience proves this” = “experience proofsless” This wasn't a huge obstacle but it is something that should be kept in mind. The next aspect that should be noted was the .txt file was all one sentence. This also wasn't a huge problem in my case, although once again it is something to keep in mind. I then proceeded to hit “command+f” and typed “code” and there it was, the “code word”.

Worked like a charm!!

Next steps: I realized that some of the words within the presentation were pretty difficult for the AI to transcribe. Something I can do in the future is write a script to transcribe each audio file individually in which case I can find the specific slide the audio was associated with.
