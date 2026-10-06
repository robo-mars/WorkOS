FROM golang:1.25-alpine AS build
WORKDIR /src
COPY gateway-go/go.mod gateway-go/go.sum ./
RUN go mod download
COPY gateway-go .
RUN CGO_ENABLED=0 go build -o /gateway ./cmd/server
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /gateway /gateway
EXPOSE 8080
ENTRYPOINT ["/gateway"]
