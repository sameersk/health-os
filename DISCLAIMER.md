# Disclaimer & Conditions of Use

**By downloading, deploying, or using this software ("Health OS") you acknowledge and accept all of the following. If you do not accept these terms, do not use the software.**

## 1. Not a medical device, not medical advice

Health OS is a personal informatics hobby project. It is **not** a medical device and has not been evaluated, cleared, or approved by the FDA, EMA, CDSCO, or any other regulatory body. Nothing it displays — including "healthspan age", system scores, nutrient coverage, or recommendations — is medical advice, diagnosis, or treatment. The models are transparent heuristics built on published population studies; they are **not** validated clinical instruments, and population-level statistics do not predict individual outcomes. Always consult a qualified healthcare professional before making health, exercise, supplement, or diet decisions, especially if you have any medical condition. Never disregard professional medical advice because of something this software displayed.

## 2. Unofficial Garmin integration — account risk

This project uses the community `garminconnect` Python library, an **unofficial, reverse-engineered client**. It is not endorsed by, affiliated with, or supported by Garmin Ltd. Using it may violate Garmin Connect's Terms of Service. Possible consequences include rate-limiting, login challenges, or **suspension or termination of your Garmin account**. You alone accept this risk. Garmin may change its API at any time, breaking this software without notice.

## 3. Credential and data security is your responsibility

Your Garmin email and password are stored in **plaintext** in a local file, and an authenticated session object is cached on disk. The bundled server has **no authentication** and is intended strictly for `127.0.0.1`. If you expose it to a network, deploy it to a server, commit your credentials, or run it on a shared machine, the resulting compromise of your credentials or health data is entirely your responsibility. The authors provide **no security guarantees** of any kind.

## 4. Data accuracy

Wrist-wearable measurements (sleep staging, HRV, stress, body battery, VO₂max estimates) have known accuracy limitations versus clinical instruments. AI-estimated nutrition values can be wrong by 30–50% or more. Scores and recommendations computed from inaccurate inputs will themselves be inaccurate. Do not rely on this software for any decision with health, safety, legal, or financial consequences.

## 5. No warranty; limitation of liability

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, ACCURACY, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS, COPYRIGHT HOLDERS, OR CONTRIBUTORS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY — INCLUDING WITHOUT LIMITATION PERSONAL INJURY, HEALTH OUTCOMES, LOSS OF DATA, LOSS OF ACCOUNTS, OR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES — WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR ITS USE. YOU ASSUME TOTAL RESPONSIBILITY AND RISK FOR YOUR USE OF THE SOFTWARE.

## 6. Indemnity

You agree to indemnify and hold harmless the authors and contributors from any claims, damages, or expenses (including legal fees) arising from your use, misuse, deployment, or distribution of this software.

## 7. Not affiliated

Garmin®, Garmin Connect™, WHOOP®, and any other trademarks referenced are the property of their respective owners. References are descriptive only and imply no affiliation or endorsement.
