
const fs = require("fs");
const dns = require("dns").promises;

const AWS = require("aws-sdk");
const fetch = require("node-fetch");

const puppeteer = require("puppeteer-core");

const utils = require("./utils");
const setStatus = utils.setStatus;

const OUTPUT_FILE = "/tmp/out/archive.wacz";
const PAGE_TIMEOUT = 120000;


// ================================================================================================
class Driver
{
  constructor(captureUrl, storageUrl) {
    this.captureUrl = captureUrl;
    this.storageUrl = storageUrl;
    this.browserHost = process.env.BROWSER_HOST || "localhost";
    this.proxyHost = process.env.PROXY_HOST;
    this.proxyPort = process.env.PROXY_PORT || 8080;
    this.proxyOrigin = `http://${this.proxyHost}:${this.proxyPort}`;

    this.done = false;

    this.currentSize = 0;
    this.pendingSize = 0;
    this.statusText = "";
    this.errored = null;

    this.entryUrl = null;
  }

  async run() {
    try {
      if (!await this.initBrowser()) {
        return;
      }

      await this.runCapture(this.page);

      await this.finish();
    } catch (e) {
      console.log("Capture Failed");
      console.warn(e);
      process.exit(1);
    }
  }

  async initBrowser() {
    if (!this.captureUrl) {
      setStatus("No URL, exiting...");
      return false;
    }
  
    setStatus("Loading Browser...");
  
    const { address: hostname } = await dns.lookup(this.browserHost);
  
    let browser = null;
  
    if (!process.env.BROWSER_HOST) {
      browser = await puppeteer.launch({headless: false, defaultViewport: null, executablePath: process.env.EXE_PATH,
        args: ["--disable-features=site-per-process"]});
    }

    const defaultViewport = this.getDefaultViewport();
    const browserURL = `http://${hostname}:9222`;
  
    while (!browser) {
      try {
        browser = await puppeteer.connect({browserURL, defaultViewport});
      } catch (e) {
        //console.log(e);
        await utils.sleep(100);
      }
    }

    this.browser = browser;

    const pages = await browser.pages();

    this.page = pages.length ? pages[0] : await browser.newPage();

    return true;
  }

  async runCapture(page) {
    if (process.env.DISABLE_CACHE) {
      setStatus(`Disabling Cache`);

      await page.setCacheEnabled(false);
      await page._client.send('Network.setBypassServiceWorker', {bypass: true});
    }

    this.playerDone = {};
    this.players = {};

    await page._client.send('Media.enable');
    await page._client.on('Media.playerEventsAdded', (params) => {
      const player = params.playerId;

      for (const e of params.events) {
        try {
          const value = JSON.parse(e.value);

          if (value.event === "kEnded") {
            console.log(`Player ${player} finished!`);
            this.playerDone[player]();
          }

          if (value.event === "kPlay" && !this.players[player]) {
            this.players[player] = new Promise((resolve, reject) => {
              console.log(`Wait for player ${player}`);
              this.playerDone[player] = resolve;
            });
          }
        } catch(e) {
          console.log(e);
        }
      }
    });

    let sleepTime = 100;

    await page._client.on('Media.playersCreated', (params) => {
      for (const player of params.players) {
        console.log(`Player created ${player}`);
        sleepTime = 3000;
      }
    });

    setStatus(`Loading Page: ${this.captureUrl}`);

    try {
      await page.goto(this.captureUrl, {"waitUntil": "networkidle0", "timeout": PAGE_TIMEOUT});
    } catch (e) {
      console.log(e);
    }

    setStatus(`Loaded`);

    this.entryUrl = this.captureUrl;

    // TODO: move to behavior system
    if (this.captureUrl.match(/https?:\/\/twitter.com/)) {
      try {
        //await page.evaluate(() => document.querySelector("div[aria-label='Play this video']").click());
        await page.evaluate(() => document.evaluate("//div[starts-with(@aria-label, 'Play')]",
            document.body, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE).singleNodeValue.click());

        sleepTime = 3000;
        this.players["_idletimer"] = utils.waitForNet(page, 5000);

      } catch (e) {
        console.log("No playable twitter video found");
      }
    }
  
    await utils.sleep(sleepTime);

    const players = Object.values(this.players);
    if (players.length) {
      await Promise.race([Promise.all(players), utils.sleep(PAGE_TIMEOUT)]);
    }
  }

  async exitBrowser() {
    if (process.env.EXIT_FILE) {
      console.log("Creating exit file: " + process.env.EXIT_FILE);
      fs.closeSync(fs.openSync(process.env.EXIT_FILE, "w"));
    }
    
    try {
      console.log("Closing Browser...");
      await this.browser.close();

    } catch (e) {
      console.log(e);
    }
  }

  async finish() {
    await this.exitBrowser();

    setStatus("Finishing Capture...");

    let res = 0;

    if (this.proxyHost) {
      await Promise.race([this.waitFileDone(`${this.proxyOrigin}/api/pending`), utils.sleep(15000)]);

      res = await this.commitWacz(this.entryUrl || this.captureUrl);
    }

    try {
      await fetch(`${this.proxyOrigin}/api/exit`);
    } catch (e) {
      console.log(e);
    }

    try {
      await fetch("http://localhost:6082/exit");
    } catch (e) {
      console.log(e);
    }

    this.done = true;
    setStatus("Done!");

    process.exit(res);
  }

  getDefaultViewport() {
    return null;
  }
  
  async commitWacz(url) {
    const usp = new URLSearchParams();
    usp.set("url", url);
  
    setStatus("Requesting WACZ");
    const resp = await fetch(`${this.proxyOrigin}/api/wacz/capture?${usp.toString()}`);
  
    if (resp.status !== 200) {
      console.log("error", await resp.text());
      return;
    }
  
    try {
      const res = await this.uploadFile();
      console.log(res);
      return 0;
    } catch (err) {
      console.log(err);
      return 1;
    }
  }
  
  uploadFile() {
    const accessKeyId =  process.env.AWS_ACCESS_KEY_ID;
    const secretAccessKey = process.env.AWS_SECRET_ACCESS_KEY;
  
    // Configure client for use with Spaces
    let endpoint = null;
  
    if (process.env.AWS_ENDPOINT) {
      endpoint = new AWS.Endpoint(process.env.AWS_ENDPOINT);
    }
  
    const s3 = new AWS.S3({
      endpoint,
      accessKeyId,
      secretAccessKey
    });
  
    const uu = new URL(this.storageUrl);
  
    var params = {
      Body: fs.createReadStream(OUTPUT_FILE),
      Bucket: uu.hostname,
      Key: uu.pathname.slice(1),
    };

    if (process.env.ACL) {
      params.ACL = process.env.ACL;
    }

    setStatus("Uploading WACZ: " + OUTPUT_FILE);
  
    return new Promise((resolve, reject) => {
      s3.putObject(params, (err, data) => {
        if (err) {
          reject(err);
        } else {
          resolve(data);
        }
      });
    });
  }

  async waitFileDone(pendingCheckUrl) {
    while (true) {
      //const oldCurrentSize = this.currentSize;
  
      let res = await fetch(pendingCheckUrl);
      res = await res.json();

      console.log(`Pending: ${JSON.stringify(res)}`);
  
      const oldPending = res.count;
      this.pendingSize = res.size;
  
      await utils.sleep(1000);
  
      res = await fetch(pendingCheckUrl);
      res = await res.json();
  
      const newPending = res.count;
      const newPendingSize = res.size;
  
      if (oldPending <= 0 && newPending <= 0 && newPendingSize === this.pendingSize) {
        return true;
      }

      if (oldPending == newPending && this.pendingSize == newPendingSize && newPending <= 2) {
        return true;
      }
    }
  }
}

module.exports = { Driver };
