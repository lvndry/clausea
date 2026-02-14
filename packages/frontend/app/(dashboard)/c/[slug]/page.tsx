"use client";

import { AlertCircle, ArrowLeft, MessageSquare } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import posthog from "posthog-js";

import { useEffect, useRef, useState } from "react";

import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessage } from "@/components/chat/chat-message";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useUser } from "@clerk/nextjs";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface Conversation {
  id: string;
  title: string;
  product_name: string;
  company_name?: string | null;
  messages: Message[];
}

export default function ChatPage() {
  const params = useParams();
  const slug = params.slug as string;
  const router = useRouter();
  const { user } = useUser();
  const scrollRef = useRef<HTMLDivElement>(null);

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isConversationId = /^[a-zA-Z0-9]{22}$/.test(slug);

  useEffect(() => {
    if (!isConversationId) {
      router.replace(`/products/${slug}`);
      return;
    }

    async function fetchConversation() {
      try {
        const res = await fetch(`/api/conversations/${slug}`);
        if (!res.ok) throw new Error("Conversation not found");
        const data = await res.json();
        setConversation(data);
        setMessages(data.messages || []);
      } catch (err) {
        console.error(err);
        setError("Failed to load conversation");
      } finally {
        setLoading(false);
      }
    }

    fetchConversation();
  }, [slug, isConversationId, router]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  async function handleSendMessage(content: string) {
    if (!conversation) return;

    // Track chat message sent event
    posthog.capture("chat_message_sent", {
      conversation_id: conversation.id,
      product_name: conversation.product_name,
      message_length: content.length,
      messages_count: messages.length + 1,
    });

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    try {
      const res = await fetch(
        `/api/conversations/${conversation.id}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: content }),
        },
      );

      if (!res.ok) throw new Error("Failed to send message");

      const data = await res.json();
      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.ai_message.content,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      console.error(err);
      posthog.captureException(err);
    } finally {
      setSending(false);
    }
  }

  if (!isConversationId) return null;

  if (loading) {
    return (
      <div className="flex h-full flex-col space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>
        <div className="flex-1 space-y-4">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
        </div>
        <Skeleton className="h-14 w-full rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="max-w-md"
        >
          <Alert variant="destructive" className="rounded-2xl">
            <AlertCircle className="h-5 w-5" />
            <AlertTitle className="font-semibold">Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-4 pb-6 border-b border-border/50"
      >
        <Link href="/products">
          <Button
            variant="ghost"
            size="icon"
            className="rounded-xl h-10 w-10 shrink-0 hover:bg-muted"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex items-center gap-3 flex-1">
          <div className="w-10 h-10 rounded-xl bg-linear-to-br from-primary/20 to-secondary/20 flex items-center justify-center">
            <MessageSquare className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold font-display">
              {conversation?.title || "Chat"}
            </h1>
            <div className="flex items-center gap-2">
              <Badge variant="outline" size="sm">
                {conversation?.product_name}
              </Badge>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Messages */}
      <ScrollArea className="flex-1 py-6">
        <div className="flex flex-col gap-4 pb-4 max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center py-20 text-center"
            >
              <div className="w-16 h-16 rounded-2xl bg-muted/50 flex items-center justify-center mb-4">
                <MessageSquare className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <h3 className="font-semibold text-lg mb-1">
                Start a conversation
              </h3>
              <p className="text-muted-foreground text-sm max-w-sm">
                Ask questions about the privacy policy or terms of service for{" "}
                {conversation?.product_name}.
              </p>
            </motion.div>
          ) : (
            messages.map((msg, index) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                <ChatMessage message={msg} />
              </motion.div>
            ))
          )}
          {sending && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-sm text-muted-foreground"
            >
              <div className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-primary/50 animate-bounce" />
                <span
                  className="w-2 h-2 rounded-full bg-primary/50 animate-bounce"
                  style={{ animationDelay: "0.1s" }}
                />
                <span
                  className="w-2 h-2 rounded-full bg-primary/50 animate-bounce"
                  style={{ animationDelay: "0.2s" }}
                />
              </div>
              <span>AI is thinking...</span>
            </motion.div>
          )}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="pt-4 border-t border-border/50"
      >
        <div className="mx-auto max-w-3xl">
          <Card variant="glass" className="p-2 rounded-2xl">
            <ChatInput
              onSend={handleSendMessage}
              disabled={sending}
              placeholder={`Ask about ${conversation?.product_name}...`}
            />
          </Card>
        </div>
      </motion.div>
    </div>
  );
}
