/**
 * @typedef {{
 *   tcString: string,
 *   tcfPolicyVersion: 2,
 *   cmpId: 1000,
 *   cmpVersion: 1000,
 *   gdprApplies: boolean | undefined,
 *   eventStatus: string,
 *   cmpStatus: string,
 *   listenerId: number | undefined,
 *   isServiceSpecific: boolean,
 *   useNonStandardStacks: boolean,
 *   publisherCC: string,
 *   purposeOneTreatment: boolean,
 *   purpose: {
 *     consents: {
 *       [purposeid]: boolean
 *     },
 *     legitimateInterests: {
 *       [purposeid]: boolean
 *     }
 *   },
 *   vendor: {
 *     consents: {
 *       [vendorid]: boolean
 *     },
 *     legitimateInterests: {
 *       [vendorid]: boolean
 *     }
 *   },
 *   specialFeatureOptins: {
 *     [specialfeatureid]: boolean
 *   },
 *   publisher: {
 *     consents: {
 *       [purposeid]: boolean
 *     },
 *     legitimateInterests: {
 *       [purposeid]: boolean
 *     },
 *     customPurpose: {
 *       consents: {
 *         [purposeid]: boolean
 *       },
 *       legitimateInterests: {
 *         [purposeid]: boolean
 *       },
 *     },
 *     restrictions: {
 *       [purposeid]: {
 *         [vendorid]: 1
 *       }
 *     }
 *   }
 * }} TCData
 */

class InMobiHandler {
  static uspStubFunction (...args) {
    if(typeof window.__uspapi !== InMobiHandler.uspStubFunction) {
      setTimeout(function() {
        if(typeof window.__uspapi !== 'undefined') {
          window.__uspapi.apply(window.__uspapi, args);
        }
      }, 500);
    }
  }

  /**
   * Initializes the `IFRAME` for the CMP, sets up event handler
   * and builds a stub to catch pre-init commands
   */
  static makeStub() {
    const TCF_LOCATOR_NAME = '__tcfapiLocator'
    const queue = []
    let win = window
    let cmpFrame

    /**
     * Looks for the top `Window` and if there is no existing embedder frame it creates one
     * @returns {boolean}
     */
    function addFrame() {
      const doc = win.document
      const otherCMP = !!(win.frames[ TCF_LOCATOR_NAME ])

      if(!otherCMP) {
        if(doc.body) {
          const iframe = doc.createElement('iframe')

          iframe.style.cssText = 'display:none'
          iframe.name = TCF_LOCATOR_NAME
          doc.body.appendChild(iframe)
        } else {
          setTimeout(addFrame, 5)
        }
      }
      return !otherCMP;
    }

    /**
     * TCF API Stub handler
     *
     * @param {string} command
     * @param {number} version
     * @param {function} [callback]
     * @param {any} [parameter]
     * @returns {*[]}
     */
    function tcfAPIHandler(command, version, callback, parameter) {
      let gdprApplies

      if(!command) {
        return queue
      }
      if (!callback) {
        callback = () => {}
      }

      switch (command) {
        case 'setGdprApplies':
          if(
            parameter !== undefined &&
            version === 2 &&
            typeof parameter === 'boolean'
          ) {
            gdprApplies = parameter;
            if(typeof callback === 'function') {
              callback('set', true);
            }
          }
          break
        case 'ping':
          const retr = {
            gdprApplies,
            cmpLoaded: false,
            cmpStatus: 'stub'
          }

          if(typeof callback === 'function') {
            callback(retr);
          }
          break;
        case 'init':
          if (typeof parameter === 'object') {
            parameter.tag_version = 'V3'
          }
        default:
          queue.push([command, version, callback, parameter]);
      }
    }

    /**
     * InMobi event handler to communicate with the inframe
     * @param {MessageEvent} event
     */
    function postMessageEventHandler(event) {
      const msgIsString = typeof event.data === 'string'
      let json = {}

      try {
        json = msgIsString ? JSON.parse(event.data) : event.data
      } catch(ignore) { // possibly unknown message broadcasted by other iframes
        // console.warn('[InMobi]: unprocessable event data received: ', event.data)
      }

      let payload = json.__tcfapiCall

      if(payload) {
        window.__tcfapi(
          payload.command,
          payload.version,
          function(retValue, success) {
            let returnMsg = {
              __tcfapiReturn: {
                returnValue: retValue,
                success: success,
                callId: payload.callId
              }
            }
            if(msgIsString) {
              returnMsg = JSON.stringify(returnMsg)
            }
            if(event && event.source && event.source.postMessage) {
              event.source.postMessage(returnMsg, '*')
            }
          },
          payload.parameter
        )
      }
    }

    while(win) {
      try {
        if(win.frames[ TCF_LOCATOR_NAME ]) {
          cmpFrame = win;
          break;
        }
      } catch(ignore) {}

      if(win === window.top) {
        break
      }
      win = win.parent
    }

    if(!cmpFrame) {
      addFrame()
      win.__tcfapi = tcfAPIHandler
      win.addEventListener('message', postMessageEventHandler, false)
    }
  }
  static makeGppStub() {
    const CMP_ID = 10;
    const SUPPORTED_APIS = [
      '2:tcfeuv2',
      '6:uspv1',
      '7:usnatv1',
      '8:usca',
      '9:usvav1',
      '10:uscov1',
      '11:usutv1',
      '12:usctv1'
    ];
    window.__gpp_addFrame = function (n) {
      if (!window.frames[n]) {
        if (document.body) {
          var i = document.createElement("iframe");
          i.style.cssText = "display:none";
          i.name = n;
          document.body.appendChild(i);
        } else {
          window.setTimeout(window.__gpp_addFrame, 10, n);
        }
      }
    };
    window.__gpp_stub = function () {
      var b = arguments;
      __gpp.queue = __gpp.queue || [];
      __gpp.events = __gpp.events || [];
      if (!b.length || (b.length == 1 && b[0] == "queue")) {
        return __gpp.queue;
      }
      if (b.length == 1 && b[0] == "events") {
        return __gpp.events;
      }
      var cmd = b[0];
      var clb = b.length > 1 ? b[1] : null;
      var par = b.length > 2 ? b[2] : null;
      if (cmd === "ping") {
        clb(
          {
            gppVersion: "1.1", // must be “Version.Subversion”, current: “1.1”
            cmpStatus: "stub", // possible values: stub, loading, loaded, error
            cmpDisplayStatus: "hidden", // possible values: hidden, visible, disabled
            signalStatus: "not ready", // possible values: not ready, ready
            supportedAPIs: SUPPORTED_APIS, // list of supported APIs
            cmpId: CMP_ID, // IAB assigned CMP ID, may be 0 during stub/loading
            sectionList: [],
            applicableSections: [-1],
            gppString: "",
            parsedSections: {},
          },
          true
        );
      } else if (cmd === "addEventListener") {
        if (!("lastId" in __gpp)) {
          __gpp.lastId = 0;
        }
        __gpp.lastId++;
        var lnr = __gpp.lastId;
        __gpp.events.push({
          id: lnr,
          callback: clb,
          parameter: par,
        });
        clb(
          {
            eventName: "listenerRegistered",
            listenerId: lnr, // Registered ID of the listener
            data: true, // positive signal
            pingData: {
              gppVersion: "1.1", // must be “Version.Subversion”, current: “1.1”
              cmpStatus: "stub", // possible values: stub, loading, loaded, error
              cmpDisplayStatus: "hidden", // possible values: hidden, visible, disabled
              signalStatus: "not ready", // possible values: not ready, ready
              supportedAPIs: SUPPORTED_APIS, // list of supported APIs
              cmpId: CMP_ID, // list of supported APIs
              sectionList: [],
              applicableSections: [-1],
              gppString: "",
              parsedSections: {},
            },
          },
          true
        );
      } else if (cmd === "removeEventListener") {
        var success = false;
        for (var i = 0; i < __gpp.events.length; i++) {
          if (__gpp.events[i].id == par) {
            __gpp.events.splice(i, 1);
            success = true;
            break;
          }
        }
        clb(
          {
            eventName: "listenerRemoved",
            listenerId: par, // Registered ID of the listener
            data: success, // status info
            pingData: {
              gppVersion: "1.1", // must be “Version.Subversion”, current: “1.1”
              cmpStatus: "stub", // possible values: stub, loading, loaded, error
              cmpDisplayStatus: "hidden", // possible values: hidden, visible, disabled
              signalStatus: "not ready", // possible values: not ready, ready
              supportedAPIs: SUPPORTED_APIS, // list of supported APIs
              cmpId: CMP_ID, // CMP ID
              sectionList: [],
              applicableSections: [-1],
              gppString: "",
              parsedSections: {},
            },
          },
          true
        );
      } else if (cmd === "hasSection") {
        clb(false, true);
      } else if (cmd === "getSection" || cmd === "getField") {
        clb(null, true);
      }
      //queue all other commands
      else {
        __gpp.queue.push([].slice.apply(b));
      }
    };
    window.__gpp_msghandler = function (event) {
      var msgIsString = typeof event.data === "string";
      try {
        var json = msgIsString ? JSON.parse(event.data) : event.data;
      } catch (e) {
        var json = null;
      }
      if (typeof json === "object" && json !== null && "__gppCall" in json) {
        var i = json.__gppCall;
        window.__gpp(
          i.command,
          function (retValue, success) {
            var returnMsg = {
              __gppReturn: {
                returnValue: retValue,
                success: success,
                callId: i.callId,
              },
            };
            event.source.postMessage(msgIsString ? JSON.stringify(returnMsg) : returnMsg, "*");
          },
          "parameter" in i ? i.parameter : null,
          "version" in i ? i.version : "1.1"
        );
      }
    };
    if (!("__gpp" in window) || typeof window.__gpp !== "function") {
      window.__gpp = window.__gpp_stub;
      window.addEventListener("message", window.__gpp_msghandler, false);
      window.__gpp_addFrame("__gppLocator");
    }
  }

  /**
   *
   * @param {string} inMobiId
   * @param {string} [host] defaults to `window.location.hostname`
   * @param {Function} [readyCallback] callback called after InMobi init
   */
  static init(inMobiId, host, readyCallback) {
    host = host || window.location.hostname
    console.log('[InMobi] initializing for domain: ', host)
    const element = document.createElement('script')
    const firstScript = document.getElementsByTagName('script')[0]
    const url = 'https://cmp.inmobi.com'.concat('/choice/', inMobiId, '/', host, '/choice.js?tag_version=V3')

    let uspTries = 0
    const uspTriesLimit = 12

    element.async = true
    element.type = 'text/javascript'
    element.src = url

    firstScript.parentNode.insertBefore(element, firstScript)

    this.makeStub() // needs to be added to catch calls before script load
    this.makeGppStub();

    let uspInterval;

    if(typeof window.__uspapi === 'undefined') {
      window.__uspapi = InMobiHandler.uspStubFunction

      uspInterval = setInterval(() => {
          uspTries++;
          if(window.__uspapi === InMobiHandler.uspStubFunction && uspTries < uspTriesLimit) {
            console.warn('[InMobi]: unable to load USP')
            return
          }

          clearInterval(uspInterval)
        }, 6000
      )

      const callback =
        /**
         * @param {TCData} tcData
         * @param {boolean} success
         */
          (tcData, success) => {
          if(success && tcData.eventStatus === 'tcloaded') {
            __tcfapi('removeEventListener', 2, (success) => {
              if(success && typeof readyCallback === 'function') {
                readyCallback()
              }
            }, tcData.listenerId);
          } else {
            console.log(' [InMobi::debug] tcfapi event: ', { tcData, success })
            if (success && typeof readyCallback === 'function' && tcData?.eventStatus === 'useractioncomplete' && tcData?.cmpStatus === 'loaded') {
              readyCallback();
            }
          }
        }

      __tcfapi('addEventListener', 2, callback)
    }
  }
}
