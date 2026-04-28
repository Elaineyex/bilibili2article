import asyncio
import os
import qrcode
import qrcode_terminal
from bilibili_api import Credential, login_v2
from dotenv import set_key, load_dotenv

load_dotenv()

async def main():
    # 1. Initialize QR login
    print("Initializing QR code login...")
    qr_login = login_v2.QrCodeLogin()
    await qr_login.generate_qrcode()

    # Get the QR link
    qr_link = qr_login._QrCodeLogin__qr_link
    print(f"\nQR Code Link: {qr_link}")

    # 2. Show QR code in terminal
    print("\nScan this QR code with your Bilibili app:")
    qrcode_terminal.draw(qr_link)

    # Also save as image (optional)
    img = qrcode.make(qr_link)
    img.save("qrcode.png")

    print("\nWaiting for scan (checking every 2 seconds)...")

    # 3. Wait for scan
    credential = None
    timeout_counter = 0
    max_timeout = 60 # 2 minutes

    while timeout_counter < max_timeout:
        status = await qr_login.check_state()

        if status == login_v2.QrCodeLoginEvents.DONE:
            print("\nLogin successful!")
            credential = qr_login.get_credential()
            break
        elif status == login_v2.QrCodeLoginEvents.TIMEOUT:
            print("\nQR code expired.")
            break
        elif status == login_v2.QrCodeLoginEvents.SCAN:
            print("Scanned, please confirm on your phone...", end="\r")
        elif status == login_v2.QrCodeLoginEvents.CONF:
            print("Confirmed! Finalizing login...       ", end="\r")

        await asyncio.sleep(2)
        timeout_counter += 1

    # 4. Save ALL relevant keys to .env
    if credential:
        env_path = ".env"
        if not os.path.exists(env_path):
            with open(env_path, 'w') as f:
                pass

        # Extract attributes from credential object
        keys_to_save = {
            "SESSDATA": credential.sessdata,
            "BILI_JCT": credential.bili_jct,
            "BUVID3": credential.buvid3,
            "BUVID4": credential.buvid4,
            "DEDEUSERID": credential.dedeuserid,
            "AC_TIME_VALUE": credential.ac_time_value
        }

        missing_keys = []
        for k, v in keys_to_save.items():
            if v:
                set_key(env_path, k, str(v))
                print(f"Updated {k} in {env_path}")
            else:
                missing_keys.append(k)

        if os.path.exists("qrcode.png"):
            os.remove("qrcode.png")

        print("\nSuccessfully updated .env with the credentials returned by Bilibili.")
        if missing_keys:
            print(
                "Bilibili did not return these optional refresh fields: "
                + ", ".join(missing_keys)
            )
            print("Login can still work, but silent refresh may be unavailable.")
        else:
            print("Silent refresh should now work for future sessions.")
    else:
        print("\nLogin failed or timed out.")

if __name__ == "__main__":
    asyncio.run(main())
