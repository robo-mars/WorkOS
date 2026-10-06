package api

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"io"
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Config struct {
	AgentURL, SessionSecret, ServiceToken, LoginCode, Origin string
	Demo, SecureCookies                                      bool
	Limit                                                    int
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func FromEnv() Config {
	return Config{AgentURL: env("AGENT_URL", "http://127.0.0.1:8000"), SessionSecret: os.Getenv("SESSION_SECRET"), ServiceToken: os.Getenv("SERVICE_TOKEN"), LoginCode: os.Getenv("LOGIN_CODE"), Origin: env("WEB_ORIGIN", "http://localhost:5173"), Demo: os.Getenv("DEMO_MODE") == "true", SecureCookies: os.Getenv("SECURE_COOKIES") == "true", Limit: 60}
}

type session struct {
	User    string `json:"user"`
	Expires int64  `json:"expires"`
}

func sign(data, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(data))
	return hex.EncodeToString(mac.Sum(nil))
}
func token(secret string) string {
	b, _ := json.Marshal(session{"demo-employee", time.Now().Add(8 * time.Hour).Unix()})
	data := base64.RawURLEncoding.EncodeToString(b)
	return data + "." + sign(data, secret)
}
func verify(value, secret string) (string, bool) {
	parts := strings.Split(value, ".")
	if len(parts) != 2 || !hmac.Equal([]byte(parts[1]), []byte(sign(parts[0], secret))) {
		return "", false
	}
	b, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return "", false
	}
	var s session
	if json.Unmarshal(b, &s) != nil || s.Expires <= time.Now().Unix() || s.User == "" {
		return "", false
	}
	return s.User, true
}

type bucket struct {
	Count int
	Start time.Time
}
type limiter struct {
	sync.Mutex
	Items map[string]bucket
	Limit int
}

func (l *limiter) allow(key string) bool {
	l.Lock()
	defer l.Unlock()
	now := time.Now()
	if len(l.Items) > 1000 {
		for k, b := range l.Items {
			if now.Sub(b.Start) > time.Minute {
				delete(l.Items, k)
			}
		}
	}
	b := l.Items[key]
	if now.Sub(b.Start) > time.Minute {
		b = bucket{Start: now}
	}
	b.Count++
	l.Items[key] = b
	return b.Count <= l.Limit
}
func New(cfg Config) (http.Handler, error) {
	if len(cfg.SessionSecret) < 32 || len(cfg.ServiceToken) < 16 {
		return nil, errors.New("SESSION_SECRET (32+ characters) and SERVICE_TOKEN (16+) are required")
	}
	if cfg.Demo && len(cfg.LoginCode) < 8 {
		return nil, errors.New("demo login requires LOGIN_CODE of at least 8 characters")
	}
	target, err := url.Parse(cfg.AgentURL)
	if err != nil || target.Host == "" {
		return nil, errors.New("invalid AGENT_URL")
	}
	if cfg.Limit == 0 {
		cfg.Limit = 60
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())
	_ = r.SetTrustedProxies(nil)
	limit := &limiter{Items: map[string]bucket{}, Limit: cfg.Limit}
	r.Use(func(c *gin.Context) {
		start := time.Now()
		id := make([]byte, 12)
		_, _ = rand.Read(id)
		requestID := hex.EncodeToString(id)
		c.Header("X-Request-ID", requestID)
		c.Header("X-Content-Type-Options", "nosniff")
		c.Header("Cache-Control", "no-store")
		c.Request.Header.Set("X-Request-ID", requestID)
		c.Next()
		slog.Info("http_request", "request_id", requestID, "method", c.Request.Method, "path", c.Request.URL.Path, "status", c.Writer.Status(), "duration_ms", time.Since(start).Milliseconds())
	})
	r.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })
	api := r.Group("/api")
	api.Use(func(c *gin.Context) {
		if !limit.allow(c.ClientIP()) {
			c.Header("Retry-After", "60")
			c.AbortWithStatusJSON(429, gin.H{"error": "Too many requests; retry in one minute."})
			return
		}
		if c.Request.Method != "GET" && c.Request.Method != "HEAD" {
			origin := c.GetHeader("Origin")
			if origin != "" && origin != cfg.Origin {
				c.AbortWithStatusJSON(403, gin.H{"error": "Origin rejected"})
				return
			}
			if c.GetHeader("Sec-Fetch-Site") == "cross-site" {
				c.AbortWithStatus(403)
				return
			}
		}
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 16*1024)
		c.Next()
	})
	api.POST("/session", func(c *gin.Context) {
		if !cfg.Demo {
			c.JSON(403, gin.H{"error": "Demo login disabled. Configure an enterprise identity adapter before public deployment."})
			return
		}
		var body struct {
			Code string `json:"code"`
		}
		if c.ShouldBindJSON(&body) != nil || subtle.ConstantTimeCompare([]byte(body.Code), []byte(cfg.LoginCode)) != 1 {
			c.JSON(401, gin.H{"error": "Invalid login code"})
			return
		}
		c.SetSameSite(http.SameSiteStrictMode)
		c.SetCookie("workplace_session", token(cfg.SessionSecret), 8*3600, "/", "", cfg.SecureCookies, true)
		c.JSON(200, gin.H{"user": "demo-employee", "name": "Mariam Hashmi", "mode": "demo"})
	})
	api.DELETE("/session", func(c *gin.Context) {
		c.SetSameSite(http.SameSiteStrictMode)
		c.SetCookie("workplace_session", "", -1, "/", "", cfg.SecureCookies, true)
		c.Status(204)
	})
	auth := api.Group("")
	auth.Use(func(c *gin.Context) {
		value, _ := c.Cookie("workplace_session")
		user, ok := verify(value, cfg.SessionSecret)
		if !ok {
			c.AbortWithStatusJSON(401, gin.H{"error": "Sign in to continue"})
			return
		}
		c.Set("user", user)
		c.Next()
	})
	auth.GET("/session", func(c *gin.Context) {
		c.JSON(200, gin.H{"user": c.GetString("user"), "name": "Mariam Hashmi", "mode": "demo"})
	})
	proxy := httputil.NewSingleHostReverseProxy(target)
	original := proxy.Director
	proxy.Director = func(req *http.Request) {
		original(req)
		req.URL.Path = strings.TrimPrefix(req.URL.Path, "/api")
		req.Header.Del("Cookie")
		req.Header.Del("Authorization")
	}
	proxy.Transport = &http.Transport{ResponseHeaderTimeout: 150 * time.Second, MaxIdleConns: 50, IdleConnTimeout: 60 * time.Second}
	proxy.ErrorHandler = func(w http.ResponseWriter, req *http.Request, err error) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(502)
		_, _ = io.WriteString(w, `{"error":"Agent service unavailable; please retry."}`)
	}
	forward := func(c *gin.Context) {
		c.Request.Header.Set("X-Service-Token", cfg.ServiceToken)
		c.Request.Header.Set("X-User-ID", c.GetString("user"))
		proxy.ServeHTTP(c.Writer, c.Request)
	}
	auth.POST("/runs", func(c *gin.Context) {
		b, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(413, gin.H{"error": "Request too large"})
			return
		}
		var body struct {
			Message        string `json:"message"`
			ConversationID string `json:"conversation_id"`
		}
		if json.Unmarshal(b, &body) != nil || len(strings.TrimSpace(body.Message)) < 3 || len(body.Message) > 4000 || len(body.ConversationID) > 100 {
			c.JSON(400, gin.H{"error": "Message must contain 3–4000 characters"})
			return
		}
		c.Request.Body = io.NopCloser(strings.NewReader(string(b)))
		c.Request.ContentLength = int64(len(b))
		c.Request.Header.Set("Content-Length", strconv.Itoa(len(b)))
		forward(c)
	})
	auth.GET("/runs", forward)
	auth.GET("/runs/:id", forward)
	auth.POST("/runs/:id/approval", forward)
	auth.POST("/runs/:id/retry", forward)
	auth.GET("/preferences", forward)
	auth.PUT("/preferences", forward)
	auth.DELETE("/preferences", forward)
	auth.GET("/audit", forward)
	auth.GET("/tools", forward)
	auth.GET("/resources", forward)
	auth.GET("/metrics", forward)
	return r, nil
}
