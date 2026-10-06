package api

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func config() Config {
	return Config{AgentURL: "http://localhost:1", SessionSecret: strings.Repeat("s", 32), ServiceToken: strings.Repeat("t", 20), LoginCode: "workplace-demo", Demo: true, Origin: "http://localhost:5173", Limit: 100}
}
func TestAuthAndCSRF(t *testing.T) {
	h, e := New(config())
	if e != nil {
		t.Fatal(e)
	}
	cases := []struct {
		method, path, body, origin string
		want                       int
	}{{"GET", "/api/runs", "", "", 401}, {"POST", "/api/session", `{"code":"bad"}`, "", 401}, {"POST", "/api/session", `{"code":"workplace-demo"}`, "https://evil.test", 403}, {"POST", "/api/session", `{"code":"workplace-demo"}`, "http://localhost:5173", 200}, {"GET", "/health", "", "", 200}}
	for _, tc := range cases {
		r := httptest.NewRequest(tc.method, tc.path, strings.NewReader(tc.body))
		r.Header.Set("Origin", tc.origin)
		r.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != tc.want {
			t.Errorf("%s %s got %d want %d", tc.method, tc.path, w.Code, tc.want)
		}
	}
}
func TestToken(t *testing.T) {
	s := strings.Repeat("x", 32)
	v := token(s)
	if _, ok := verify(v, s); !ok {
		t.Fatal("valid token rejected")
	}
	if _, ok := verify(v+"bad", s); ok {
		t.Fatal("tampered token accepted")
	}
	b, _ := json.Marshal(session{"a", time.Now().Add(-time.Minute).Unix()})
	d := base64.RawURLEncoding.EncodeToString(b)
	if _, ok := verify(d+"."+sign(d, s), s); ok {
		t.Fatal("expired token accepted")
	}
}
func TestProxyIdentityAndValidation(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-User-ID") != "demo-employee" {
			t.Error("identity not overwritten")
		}
		if r.Header.Get("Cookie") != "" {
			t.Error("cookie leaked")
		}
		w.WriteHeader(200)
	}))
	defer upstream.Close()
	cfg := config()
	cfg.AgentURL = upstream.URL
	h, _ := New(cfg)
	for _, body := range []string{`{"message":"hello"}`, `{"message":"x"}`} {
		r := httptest.NewRequest("POST", "/api/runs", strings.NewReader(body))
		ctx, cancel := context.WithCancel(r.Context())
		defer cancel()
		r = r.WithContext(ctx)
		r.AddCookie(&http.Cookie{Name: "workplace_session", Value: token(cfg.SessionSecret)})
		r.Header.Set("X-User-ID", "victim")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		want := 200
		if strings.Contains(body, `"x"`) {
			want = 400
		}
		if w.Code != want {
			t.Errorf("got %d want %d", w.Code, want)
		}
	}
}
func TestRateLimit(t *testing.T) {
	cfg := config()
	cfg.Limit = 1
	h, _ := New(cfg)
	for i := 0; i < 2; i++ {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest("GET", "/api/runs", nil))
		if i == 1 && w.Code != 429 {
			t.Fatal("rate limit missing")
		}
	}
}
func TestConfigFailsClosed(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatal("missing secrets accepted")
	}
}
