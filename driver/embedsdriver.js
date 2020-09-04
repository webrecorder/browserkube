const fs = require("fs");

const fetch = require("node-fetch");

const utils = require("./utils");
const setStatus = utils.setStatus;

const express = require("express");
const querystring = require("querystring");

const { Driver } = require("./driver");


// ================================================================================================
class EmbedDriver extends Driver
{
  constructor(...args) {
    super(...args);
    this.embedPort = Number(process.env.EMBED_PORT || 3000);
    this.embedHost = process.env.EMBED_HOST || "localhost";

    this.embedWidth = null;
    this.embedHeight = null;
    this.embedType = null;

    this.embedUrl = null;

    this.oembedMap = {};
    this.oembedCache = {};

    this.initOembeds();
    this.initEmbedServer();
  }

  getDefaultViewport() {
    //const oembed = await getOembed(captureUrl);
    //const viewport = {'width': oembed.width || 600, 'height': 600};
    const viewport = null;
    return viewport;
  }

  async initOembeds() {
    let data = await fs.promises.readFile("./embeds.json", {encoding: "utf8"});
    this.oembedMap = JSON.parse(data).embeds;
  
    for (let r of this.oembedMap) {
      r.rx = new RegExp(r.rx);
    }
  }
  
  findOembedRule(url) {
    for (let r of this.oembedMap) {
      if (r.rx.exec(url)) {
        return r;
      }
    }
    return null;
  }
  
  ruleToUrl(rule, url) {
    let params = rule.params || {};
    params.url = url;
    return rule.oe + "?" + querystring.stringify(params);
  }
  
  async getOembed(url) {
    const rule = this.findOembedRule(url);
  
    if (!rule) {
      return null;
    }
  
    if (this.oembedCache[url]) {
      return this.oembedCache[url];
    }
  
    let res = await fetch(this.ruleToUrl(rule, url));
  
    if (res.status != 200) {
      return null;
    }
  
    res = await res.json();
  
    this.oembedCache[url] = res;
    this.embedWidth = res.width;
    this.embedHeight = res.height;
    this.embedType = rule.name;
  
    return res;
  }

  initEmbedServer() {
    this.app = express();

    this.app.get("/screenshot", (req, res) => {
      res.sendFile("/tmp/screenshot.png");
    });
    
    this.app.get("/status", (req, res) => {
      res.json({"done": this.done,
        "error": this.errored,
        "status": this.statusText,
        "width": this.embedWidth,
        "height": this.embedHeight,
        "type": this.embedType,
        "size": this.currentSize + this.pendingSize});
    });
    
    this.app.get(/info\/(.*)/, async (req, res) => {
      const url = req.originalUrl.slice("/info/".length);
      const rule = this.findOembedRule(url);
    
      if (!rule) {
        res.sendStatus(404);
        return;
      }
    
      res.redirect(307, this.ruleToUrl(rule, url));
    });
    
    this.app.get(/e\/(.*)/, async (req, res) => {
      const url = req.originalUrl.slice("/e/".length);
      const oembed = await this.getOembed(url);
    
      if (!oembed || !oembed.html) {
        res.sendStatus(404);
        return;
      }
    
      let style = "";
    
      if (this.embedWidth) {
        style += `width: ${this.embedWidth}px;`;
      }
      if (this.embedHeight) {
        style += `height: ${this.embedHeight}px;`;
      }
    
      const content = `<div id="embedArchiveDiv" style="${style}">${oembed.html}</div>`;
    
      res.set("Content-Type", "text/html");
      res.send(content);
    });

    new Promise(() => this.app.listen(this.embedPort));
  }

  async runCapture(page) {
    //const embedPrefix = (this.embedPort === 80 ? `http://${this.embedHost}` : `http://${this.embedHost}:${this.embedPort}`);
  
    setStatus("Getting Embed Info...");
  
    //try {
    //  await page.goto(`${embedPrefix}/info/${url}`);
    //} catch (e) {
    //console.log(e);
    //}
  
    if (this.proxyHost) {
      const captureRes = await fetch(`${this.proxyOrigin}/capture/record/mp_/${this.embedPrefix}/info/${this.captureUrl}`);
  
      if (captureRes.status != 200) {
        this.errored = "invalid_embed";
        return;
      }
    }
  
    this.embedUrl = `${this.embedPrefix}/e/${this.captureUrl}`;

    this.entryUrl = this.embedUrl;
  
    setStatus("Loading Embed...");
  
    await page.goto(this.embedUrl, {"waitUntil": "networkidle0"});
  
    await utils.sleep(100);
    //const computeWidth = await page.evaluate(() => document.querySelector("body").firstElementChild.scrollWidth);
  
    setStatus("Running Behavior...");
  
    try {
      await this.runBehavior(page, this.captureUrl);
    } catch (e) {
      console.warn(e);
    }
  }

  async runBehavior(page, url) {
    const rule = this.findOembedRule(url);
  
    if (!rule) {
      console.log("no rule for: " + url);
      return false;
    }
  
    switch (rule.name) {
    case "tweet":
      await runTweet(page, this);
      break;
  
    case "instagram":
      await runIG(page, this);
      break;
  
    case "youtube":
      await runYT(page, this);
      break;
  
    case "facebook":
      await runFB(page, this);
      break;
  
    case "facebook_video":
      await runFBVideo(page, this);
    }
  
    await utils.waitForNet(page, 5000);
  
    return true;
  }

  async takeCustomCapture(page, handle) {
    utils.setStatus("Taking Screenshot...");
  
    try {
      if (!handle) {
        //handle = await page.evaluateHandle('document.body.firstElementChild');
      }
  
      handle = await page.$("#embedArchiveDiv");
  
      const embedBounds = await handle.boundingBox();
  
      await page.screenshot({"path": "/tmp/screenshot.png", clip: embedBounds, omitBackground: true});
  
      const buff = await fs.promises.readFile("/tmp/screenshot.png");
  
      await this.putCustomRecord("screenshot:" + page.url(), "image/png", buff);
    } catch (e) {
      console.warn(e);
    }
  
    // if (!useFreezeDry) {
    //   return;
    // }
  
    // utils.setStatus("Load Static Snapshot");
  
    // try {
    //   const inject = await page.addScriptTag({path: "./freeze-dry.js"});
  
    //   const html = await page.evaluate("freezeDry.default()");
  
    //   await fs.promises.writeFile("/tmp/snapshot.html", html);
  
    //   await putCustomRecord("dom:" + embedUrl, "text/html", html);
    // } catch (e) {
    //   console.warn(e);
    // }
  }

  async putCustomRecord(url, contentType, buff) {
    try {
      if (!this.proxyHost) {
        return;
      }
  
      const putUrl = `${this.proxyOrigin}/api/custom/capture?${querystring.stringify({"url": url})}`;
  
      let res = await fetch(putUrl, { method: "PUT", body: buff, headers: { "Content-Type": contentType } });
      res = await res.json();
      console.log(res);
    } catch (e)  {
      console.log(e);
    }
  }  
}








async function runTweet(page, driver) {
  const selector = "div[data-scribe=\"element:play_button\"]";

  await driver.takeCustomCapture(page);

  const res = await page.evaluate(utils.clickShadowRoot, "twitter-widget", selector);
  if (res){
    utils.setStatus("Loading Video...");
  }
  return res;
}

async function runIG(page, driver) {
  const frame = await utils.waitForFrame(page, 1);
  if (!frame) {
    console.log("no frame?");
    return false;
  }

  const liList = await frame.$$("ul > li", {timeout: 500});

  await driver.takeCustomCapture(page);

  if (liList && liList.length) {
    let first = true;

    for (let child of liList) {
      if (!first) {
        utils.setStatus("Loading Slides...");
        await utils.waitForClick(frame, "div.coreSpriteRightChevron", 500);
        await utils.sleep(1000);
      }
      first = false;

      const video = await child.$("video");

      if (video) {
        utils.setStatus("Loading Video...");
        await video.click();
        await utils.sleep(1000);
      }
    }

    return false;

  } else {
    const videos = await frame.$$("video");

    for (let video of videos) {
      try {
        utils.setStatus("Loading Video...");
        await video.click();
        await utils.sleep(1000);
      } catch (e) {
        console.log(e);
      }
    }

    return true;
  }
}

async function runYT(page, driver) {
  const frame = await utils.waitForFrame(page, 1);
  if (!frame) {
    console.log("no frame found?");
    return false;
  }

  try {
    const selector = "button[aria-label=\"Play\"]";
    await frame.waitForSelector(selector, {timeout: 10000});
    await utils.sleep(500);
    await driver.takeCustomCapture(page);
    utils.setStatus("Loading Video...");
    await frame.click(selector);

  } catch (e) {
    console.log(e);
    console.log("no play button!");
  }
    
  return true;
}

async function runFB(page, driver) {
  const frame = await utils.waitForFrame(page, 2);

  //await utils.sleep(500);
  await frame.waitForSelector("[aria-label]");
  const handle = await page.waitForSelector("div.fb-post");

  await driver.takeCustomCapture(page, handle);

  await utils.sleep(1000);

  return true;
}

async function runFBVideo(page, driver) {
  const frame = await utils.waitForFrame(page, 2);

  //await utils.sleep(500);
  await frame.waitForSelector("[aria-label]");
  const handle = await page.waitForSelector("div.fb-video");
  await driver.takeCustomCapture(page, handle);
 
  utils.setStatus("Playing Video...");
  await utils.waitForClick(frame, "input[type=button][aria-label]", 1000);

  await utils.sleep(1000);

  return true;
}

module.exports = { EmbedDriver };
