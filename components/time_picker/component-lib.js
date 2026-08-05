/* Minimal Streamlit component-lib (v1 protocol, streamlit 1.61).
 * Implements the same message contract as streamlit-component-lib 2.x:
 *   parent -> iframe : postMessage { type: "streamlit:render", args, dfs, disabled, theme }
 *   iframe -> parent : postMessage { isStreamlitMessage: true, type: "streamlit:..." }
 */
(function () {
  if (window.Streamlit) return;

  var Streamlit = {
    API_VERSION: 1,
    RENDER_EVENT: "streamlit:render",
    events: new EventTarget(),
    setComponentReady: function () {
      Streamlit.sendBackMsg("streamlit:componentReady", { apiVersion: Streamlit.API_VERSION });
    },
    setFrameHeight: function (height) {
      if (height === undefined) height = document.body.scrollHeight;
      Streamlit.sendBackMsg("streamlit:setFrameHeight", { height: height });
    },
    setComponentValue: function (value) {
      Streamlit.sendBackMsg("streamlit:setComponentValue", { value: value, dataType: "json" });
    },
    sendBackMsg: function (type, data) {
      window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data), "*");
    }
  };

  window.addEventListener("message", function (event) {
    var data = event.data || {};
    if (data.type !== Streamlit.RENDER_EVENT) return;
    var args = data.args || {};
    var eventData = {
      disabled: Boolean(data.disabled),
      args: args,
      theme: data.theme
    };
    Streamlit.events.dispatchEvent(new CustomEvent(Streamlit.RENDER_EVENT, { detail: eventData }));
  });

  window.Streamlit = Streamlit;
})();
